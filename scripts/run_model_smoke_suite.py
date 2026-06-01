#!/usr/bin/env python3
"""Run a small model-backed smoke suite against the certfix CLI.

This script is intentionally outside pytest. It runs the configured real models and can
take many minutes on a GPU machine.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class SmokeCase:
    """One self-contained C sample for model-backed smoke testing."""

    case_id: str
    source_name: str
    expected_rule: str | None
    target_kind: Literal["file", "directory"] = "file"
    run_fix: bool = True
    expect_fixed: bool = False
    notes: str = ""


@dataclass
class CommandResult:
    """Captured subprocess result."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str


CASES: tuple[SmokeCase, ...] = (
    SmokeCase(
        case_id="mem30_use_after_free",
        source_name="mem30_use_after_free.c",
        expected_rule="MEM30-C",
        expect_fixed=True,
        notes="Primary full-pipeline smoke. The expected fix moves printf before free.",
    ),
    SmokeCase(
        case_id="exp34_null_deref",
        source_name="exp34_null_deref.c",
        expected_rule="EXP34-C",
        expect_fixed=False,
        notes="Null pointer dereference candidate. Detection/selection smoke by default.",
    ),
    SmokeCase(
        case_id="exp33_uninitialized_read",
        source_name="exp33_uninitialized_read.c",
        expected_rule="EXP33-C",
        expect_fixed=False,
        notes="Uninitialized scalar read candidate.",
    ),
    SmokeCase(
        case_id="mem35_short_alloc",
        source_name="mem35_short_alloc.c",
        expected_rule="MEM35-C",
        expect_fixed=False,
        notes="Allocation size is too small for the copied string.",
    ),
    SmokeCase(
        case_id="multi_function_mem30",
        source_name="multi_function_mem30.c",
        expected_rule="MEM30-C",
        run_fix=False,
        notes="Single source file with multiple functions. Detection/selection smoke.",
    ),
    SmokeCase(
        case_id="multi_file_mem30",
        source_name="multi_file_mem30",
        expected_rule="MEM30-C",
        target_kind="directory",
        run_fix=False,
        notes="Directory target with multiple C/header files. Detection/selection smoke.",
    ),
    SmokeCase(
        case_id="clean_print",
        source_name="clean_print.c",
        expected_rule=None,
        run_fix=False,
        notes="Negative control. Should not produce violations.",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Role-based certfix config YAML")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("model-smoke-results"),
        help="Directory for JSONL, summary, and copied sample files",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=[case.case_id for case in CASES],
        help="Run only the named case. Can be repeated.",
    )
    parser.add_argument(
        "--mode",
        choices=("check", "fix", "both"),
        default="both",
        help="Run check only, fix only, or both",
    )
    parser.add_argument("--timeout", type=int, default=1200, help="Per-command timeout seconds")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero if any positive case misses its rule, any clean case reports findings, "
        "or any expect_fixed case is not fixed",
    )
    parser.add_argument(
        "--save-fixed-code",
        action="store_true",
        help="Copy generated fixed-code artifacts from certfix-output into the smoke output dir",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to run `-m certfix`",
    )
    args = parser.parse_args()

    selected = [case for case in CASES if args.case is None or case.case_id in set(args.case)]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="certfix-model-smoke-") as tmp:
        tmp_dir = Path(tmp)
        for case in selected:
            source_path = _prepare_case_source(case, tmp_dir, args.output_dir)

            record: dict[str, Any] = {
                "case": asdict(case),
                "source_path": str(source_path),
            }
            if args.mode in ("check", "both"):
                check_output_dir = args.output_dir / "artifacts" / case.case_id / "check"
                check_result = _run_certfix(
                    args.python,
                    "check",
                    source_path,
                    args.config,
                    args.timeout,
                    output_dir=check_output_dir,
                )
                record["check"] = _command_record(check_result)
                record["check_summary"] = _summarize_check(check_result)

            should_run_fix = case.run_fix and args.mode in ("fix", "both")
            if should_run_fix:
                fix_output_dir = args.output_dir / "artifacts" / case.case_id / "fix"
                fix_result = _run_certfix(
                    args.python,
                    "fix",
                    source_path,
                    args.config,
                    args.timeout,
                    output_dir=fix_output_dir,
                    rule=case.expected_rule,
                )
                record["fix"] = _command_record(fix_result)
                record["fix_artifact_dir"] = str(fix_output_dir)
                fix_summary = _summarize_fix(fix_result)
                record["fix_summary"] = fix_summary
                if args.save_fixed_code and "fixed" in fix_summary["statuses"]:
                    fixed_output = _save_fixed_source(case, fix_output_dir, args.output_dir)
                    record["fixed_source_path"] = str(fixed_output)

            records.append(record)
            _print_case(record)

    jsonl_path = args.output_dir / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = _build_summary(records)
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    print(f"\nWrote {jsonl_path}")
    print(f"Wrote {summary_path}")
    print(
        "Summary: "
        f"cases={summary['cases']} "
        f"rule_hits={summary['rule_hits']} "
        f"clean_passes={summary['clean_passes']} "
        f"fixed={summary['fixed']}"
    )

    if args.strict and summary["strict_failures"]:
        print("\nStrict failures:")
        for failure in summary["strict_failures"]:
            print(f"- {failure}")
        return 1
    return 0


def _prepare_case_source(case: SmokeCase, tmp_dir: Path, output_dir: Path) -> Path:
    """Copy a smoke case source into temp and output directories."""
    case_path = _case_root() / case.source_name
    temp_path = tmp_dir / case.source_name
    copied_output_path = output_dir / case.source_name

    if case.target_kind == "file":
        code = case_path.read_text(encoding="utf-8")
        temp_path.write_text(code, encoding="utf-8")
        copied_output_path.write_text(code, encoding="utf-8")
        return temp_path

    shutil.copytree(case_path, temp_path, dirs_exist_ok=True)
    shutil.copytree(case_path, copied_output_path, dirs_exist_ok=True)
    return temp_path


def _save_fixed_source(case: SmokeCase, fix_artifact_dir: Path, output_dir: Path) -> Path:
    """Save fixed source artifacts into the smoke output directory."""
    fixes_dir = fix_artifact_dir / "fixes"
    if case.target_kind == "file":
        fixed_output = output_dir / f"{case.case_id}.fixed.c"
        candidates = sorted(fixes_dir.rglob("*.fixed.c"))
        fixed_code = candidates[0].read_text(encoding="utf-8") if candidates else ""
        fixed_output.write_text(fixed_code, encoding="utf-8")
        return fixed_output

    fixed_output = output_dir / f"{case.case_id}.fixed"
    shutil.copytree(fixes_dir, fixed_output, dirs_exist_ok=True)
    return fixed_output


def _case_root() -> Path:
    return Path(__file__).resolve().parent.parent / "model-smoke-cases"


def _run_certfix(
    python: str,
    command: str,
    source_path: Path,
    config_path: Path,
    timeout: int,
    output_dir: Path,
    rule: str | None = None,
) -> CommandResult:
    cmd = [
        python,
        "-m",
        "certfix",
        command,
        str(source_path),
        "--config",
        str(config_path),
        "--format",
        "json",
        "--timeout",
        str(timeout),
        "--output-dir",
        str(output_dir),
    ]
    if command == "fix" and rule:
        cmd.extend(["--rule", rule])
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 30,
        )
    except subprocess.TimeoutExpired as e:
        return CommandResult(
            command=cmd,
            returncode=124,
            stdout=e.stdout or "",
            stderr=(e.stderr or "") + f"\nCommand timed out after {timeout + 30}s",
        )
    return CommandResult(
        command=cmd,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _command_record(result: CommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "returncode": result.returncode,
        "stdout_json": _parse_json(result.stdout),
        "stdout": result.stdout,
        "stderr_tail": result.stderr[-4000:],
    }


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _summarize_check(result: CommandResult) -> dict[str, Any]:
    data = _parse_json(result.stdout)
    violations: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for file_data in data.get("files", []):
            if isinstance(file_data, dict):
                violations.extend(file_data.get("violations", []))
    return {
        "returncode": result.returncode,
        "rules": [v.get("rule_id") for v in violations],
        "selected_rules": [v.get("rule_id") for v in violations if v.get("selector_decision")],
        "violations": violations,
    }


def _summarize_fix(result: CommandResult) -> dict[str, Any]:
    data = _parse_json(result.stdout)
    fixes = data.get("fixes", []) if isinstance(data, dict) else []
    return {
        "returncode": result.returncode,
        "statuses": [fix.get("status") for fix in fixes if isinstance(fix, dict)],
        "successes": [fix.get("success") for fix in fixes if isinstance(fix, dict)],
        "fixes": fixes,
    }


def _print_case(record: dict[str, Any]) -> None:
    case = record["case"]
    parts = [case["case_id"]]
    if "check_summary" in record:
        parts.append(f"check_rules={record['check_summary']['rules']}")
    if "fix_summary" in record:
        parts.append(f"fix_statuses={record['fix_summary']['statuses']}")
    print(" | ".join(parts), flush=True)


def _build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    strict_failures: list[str] = []
    rule_hits = 0
    clean_passes = 0
    fixed = 0

    for record in records:
        case = record["case"]
        expected_rule = case["expected_rule"]
        check_summary = record.get("check_summary")
        if check_summary:
            rules = check_summary["rules"]
            if expected_rule is None:
                if not rules:
                    clean_passes += 1
                else:
                    strict_failures.append(f"{case['case_id']}: expected clean, got {rules}")
            elif expected_rule in rules:
                rule_hits += 1
            else:
                strict_failures.append(
                    f"{case['case_id']}: expected {expected_rule}, got {rules}"
                )

        fix_summary = record.get("fix_summary")
        if fix_summary:
            statuses = fix_summary["statuses"]
            if "fixed" in statuses:
                fixed += 1
            if case["expect_fixed"] and "fixed" not in statuses:
                strict_failures.append(
                    f"{case['case_id']}: expected final status fixed, got {statuses}"
                )

    return {
        "cases": len(records),
        "rule_hits": rule_hits,
        "clean_passes": clean_passes,
        "fixed": fixed,
        "strict_failures": strict_failures,
    }


if __name__ == "__main__":
    raise SystemExit(main())
