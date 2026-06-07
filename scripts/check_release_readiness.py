#!/usr/bin/env python3
"""Run non-runtime release readiness checks for certfix.

This script intentionally avoids GPU, local model, and external API calls. It
checks the public packaging/config surface that should be stable before a
release candidate is tagged.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

PUBLIC_CONFIGS = [
    "configs/qwen36-mtp-local.yaml",
    "configs/qwen36-mtp-docker.yaml",
    "configs/qwen36-mtp-check.yaml",
    "configs/deepseek-v4-flash-openrouter.yaml",
    "configs/deepseek-v4-flash-api.yaml",
    "configs/gemini-3-flash-preview-openrouter.yaml",
    "configs/examples/local-detection-deepseek-fix.yaml",
    "configs/examples/local-detection-deepseek-fix-docker.yaml",
    "configs/examples/deepseek-gemini-step-overrides.yaml",
]

INTERNAL_PATTERN = re.compile(
    r"(/work/certfix|certfix-seed-generator|output/phase|run_[0-9]{8}|"
    r"checkpoint-[0-9]+|(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{10,})"
)

PUBLIC_SCAN_PATHS = [
    ".certfix.yaml.example",
    ".github/workflows/ci.yml",
    ".github/workflows/docker.yml",
    "AGENTS.md",
    "Dockerfile",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "configs/qwen36-mtp-local.yaml",
    "configs/qwen36-mtp-docker.yaml",
    "configs/qwen36-mtp-check.yaml",
    "configs/deepseek-v4-flash-openrouter.yaml",
    "configs/deepseek-v4-flash-api.yaml",
    "configs/gemini-3-flash-preview-openrouter.yaml",
    "configs/examples/local-detection-deepseek-fix.yaml",
    "configs/examples/local-detection-deepseek-fix-docker.yaml",
    "configs/examples/deepseek-gemini-step-overrides.yaml",
    "docker",
    "docker-compose.api.yml",
    "docker-compose.local-qwen36.yml",
    "src/certfix/configs",
    "docs/ARCHITECTURE.md",
    "docs/BENCHMARK_SUMMARY.md",
    "docs/CONFIGURATION.md",
    "docs/CONTRIBUTING.md",
    "docs/DESIGN_RATIONALE.md",
    "docs/DOCKER.md",
    "docs/EXAMPLE_OUTPUT.md",
    "docs/FAQ.md",
    "docs/INSTALLATION.md",
    "docs/LIMITATIONS.md",
    "docs/QWEN36_MTP_RUNTIME.md",
    "docs/INDEX.md",
    "docs/MODEL_SMOKE_SUITE.md",
    "docs/RELEASE_CHECKLIST.md",
    "docs/RESEARCH_NOTES.md",
    "docs/SUPPORTED_RULES.md",
    "docs/VALIDATION_AND_RETRY.md",
]

EXCLUDED_SAMPLE_DATA = [
    "src/certfix/data/calibration_samples.jsonl.gz",
    "src/certfix/data/juliet_samples.jsonl.gz",
    "src/certfix/data/primevul_samples.jsonl.gz",
    "src/certfix/data/test_samples.jsonl.gz",
]

EXCLUDED_PUBLIC_PATHS = [
    "CLAUDE.md",
    "docs/internal",
    "docs/research-archive",
    "eval-splits",
    *EXCLUDED_SAMPLE_DATA,
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel",
        type=Path,
        default=None,
        help="Optional wheel file to inspect. Defaults to the newest dist/certfix-*.whl.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(SRC))

    results: list[CheckResult] = []
    results.extend(check_public_config_loads())
    results.extend(check_bundled_config_profiles())
    results.append(check_config_cli_list())
    results.extend(check_public_boundary_files())
    results.extend(check_public_scan_paths())
    results.extend(check_pyproject_dependencies())
    results.extend(check_sdist_exclude_config())

    wheel = args.wheel or newest_wheel()
    if wheel is not None:
        results.extend(check_wheel(wheel))
    else:
        results.append(
            CheckResult(
                "wheel inspection",
                False,
                "No wheel found. Run `python3 -m build --sdist --wheel` first.",
            )
        )

    sdist = newest_sdist()
    if sdist is not None:
        results.extend(check_sdist(sdist))

    results.append(check_git_clean_or_known_dirty())

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"{status} {result.name}")
        if result.detail:
            print(f"     {result.detail}")

    failed = [result for result in results if not result.ok]
    if failed:
        print(f"\n{len(failed)} release readiness check(s) failed.", file=sys.stderr)
        return 1

    print("\nAll non-runtime release readiness checks passed.")
    return 0


def check_public_config_loads() -> list[CheckResult]:
    from certfix.config import Config

    results: list[CheckResult] = []
    for rel_path in PUBLIC_CONFIGS:
        path = ROOT / rel_path
        if not path.exists():
            results.append(CheckResult(f"Config.load {rel_path}", False, "file missing"))
            continue
        try:
            Config.load(path)
        except Exception as exc:  # noqa: BLE001 - release checker should report any failure
            results.append(CheckResult(f"Config.load {rel_path}", False, str(exc)))
        else:
            results.append(CheckResult(f"Config.load {rel_path}", True))
    return results


def check_bundled_config_profiles() -> list[CheckResult]:
    from certfix.cli import CONFIG_PROFILES, _read_bundled_config
    from certfix.config import Config

    results: list[CheckResult] = []
    expected_names = {
        "qwen36-mtp-local",
        "qwen36-mtp-docker",
        "qwen36-mtp-check",
        "deepseek-v4-flash-openrouter",
        "deepseek-v4-flash-api",
        "gemini-3-flash-preview-openrouter",
        "local-detection-deepseek-fix",
        "local-detection-deepseek-fix-docker",
        "deepseek-gemini-step-overrides",
    }
    actual_names = set(CONFIG_PROFILES)
    results.append(
        CheckResult(
            "bundled config profile names",
            actual_names == expected_names,
            "" if actual_names == expected_names else f"actual={sorted(actual_names)}",
        )
    )

    for profile in sorted(expected_names):
        try:
            content = _read_bundled_config(profile)
            with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                Config.load(Path(f.name))
        except Exception as exc:  # noqa: BLE001
            results.append(CheckResult(f"bundled config load {profile}", False, str(exc)))
        else:
            results.append(CheckResult(f"bundled config load {profile}", True))

    resource_root = resources.files("certfix.configs")
    for profile, resource_path in CONFIG_PROFILES.items():
        try:
            resource = resource_root.joinpath(resource_path)
            ok = resource.is_file()
        except Exception:  # noqa: BLE001
            ok = False
        results.append(
            CheckResult(
                f"bundled config resource {profile}",
                ok,
                resource_path if not ok else "",
            )
        )
    return results


def check_config_cli_list() -> CheckResult:
    expected = {
        "qwen36-mtp-local",
        "qwen36-mtp-docker",
        "qwen36-mtp-check",
        "deepseek-v4-flash-openrouter",
        "deepseek-v4-flash-api",
        "gemini-3-flash-preview-openrouter",
        "local-detection-deepseek-fix",
        "local-detection-deepseek-fix-docker",
        "deepseek-gemini-step-overrides",
    }
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{SRC}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    completed = subprocess.run(
        [sys.executable, "-m", "certfix", "config", "--list"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    listed = set(completed.stdout.splitlines())
    return CheckResult(
        "certfix config --list exposes bundled profiles",
        completed.returncode == 0 and listed == expected,
        "" if listed == expected else f"listed={sorted(listed)}",
    )


def check_public_scan_paths() -> list[CheckResult]:
    findings: list[str] = []
    for rel_path in PUBLIC_SCAN_PATHS:
        path = ROOT / rel_path
        if not path.exists():
            findings.append(f"{rel_path}: missing")
            continue
        files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
        for file_path in files:
            if "__pycache__" in file_path.parts:
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for line_number, line in enumerate(text.splitlines(), start=1):
                if INTERNAL_PATTERN.search(line):
                    findings.append(f"{file_path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    return [
        CheckResult(
            "public docs/config internal detail scan",
            not findings,
            "\n".join(findings[:20]),
        )
    ]


def check_public_boundary_files() -> list[CheckResult]:
    notices_path = ROOT / "THIRD_PARTY_NOTICES.md"
    notices = (
        notices_path.read_text(encoding="utf-8", errors="ignore")
        if notices_path.exists()
        else ""
    )
    results = [
        CheckResult(
            "third-party notices present",
            notices_path.is_file(),
            "THIRD_PARTY_NOTICES.md is required",
        ),
        CheckResult(
            "SARIF fixture notice present",
            "sarif-schema-2.1.0.json" in notices,
            "tests/fixtures/sarif-schema-2.1.0.json must be noticed",
        ),
        CheckResult(
            "CERT-C metadata notice present",
            "cert_c_rules_with_examples.json" in notices,
            "src/certfix/data/cert_c_rules_with_examples.json must be noticed",
        ),
        CheckResult(
            "evaluation dataset notice present",
            "Evaluation Datasets" in notices
            and "PrimeVul" in notices
            and "Juliet" in notices
            and "eval-splits/" in notices,
            "THIRD_PARTY_NOTICES.md must document that evaluation datasets are not bundled",
        ),
    ]
    for rel_path in EXCLUDED_PUBLIC_PATHS:
        path = ROOT / rel_path
        results.append(
            CheckResult(
                f"{rel_path} excluded from public tree",
                not path.exists(),
                f"{rel_path} should not be included in the initial public repo"
                if path.exists()
                else "",
            )
        )
    return results


def check_pyproject_dependencies() -> list[CheckResult]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    dependencies = project.get("dependencies", [])
    optional = project.get("optional-dependencies", {})

    results = [
        CheckResult(
            "base dependencies include the standard API backend",
            dependencies == [
                "click>=8.0.0",
                "httpx>=0.25.0",
                "pyyaml>=6.0",
                "rich>=13.0.0",
            ],
            f"dependencies={dependencies}",
        ),
        CheckResult(
            "api extra is not exposed",
            "api" not in optional,
            f"api={optional.get('api', [])}" if "api" in optional else "",
        ),
        CheckResult(
            "local llama-cpp extra is not exposed",
            "local" not in optional,
            f"local={optional.get('local', [])}" if "local" in optional else "",
        ),
        CheckResult(
            "detect extra is not exposed",
            "detect" not in optional,
            f"detect={optional.get('detect', [])}" if "detect" in optional else "",
        ),
        CheckResult(
            "public extras do not require legacy ML deps",
            not {
                "torch>=2.0.0",
                "transformers>=4.40.0",
                "peft>=0.10.0",
                "accelerate>=0.27.0",
            }.intersection(
                dep
                for extra in ("dev",)
                for dep in optional.get(extra, [])
            ),
            f"optional={optional}",
        ),
        CheckResult(
            "dev extra contains build",
            "build>=1.0.0" in optional.get("dev", []),
            f"dev={optional.get('dev', [])}",
        ),
    ]
    return results


def check_sdist_exclude_config() -> list[CheckResult]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    targets = data.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {})
    sdist = targets.get("sdist", {})
    excludes = set(sdist.get("exclude", []))
    expected = {
        "/CLAUDE.md",
        "/docs/internal",
        "/docs/research-archive",
        "/eval-splits",
        "/model-smoke-results",
        "/src/certfix/data/*samples.jsonl.gz",
    }
    return [
        CheckResult(
            "sdist excludes private/evaluation artifacts",
            expected <= excludes,
            f"missing={sorted(expected - excludes)}" if not expected <= excludes else "",
        )
    ]


def newest_wheel() -> Path | None:
    wheels = sorted((ROOT / "dist").glob("certfix-*.whl"), key=lambda p: p.stat().st_mtime)
    return wheels[-1] if wheels else None


def newest_sdist() -> Path | None:
    archives = sorted((ROOT / "dist").glob("certfix-*.tar.gz"), key=lambda p: p.stat().st_mtime)
    return archives[-1] if archives else None


def check_wheel(wheel: Path) -> list[CheckResult]:
    if not wheel.exists():
        return [CheckResult("wheel exists", False, str(wheel))]

    results: list[CheckResult] = [CheckResult("wheel exists", True, str(wheel))]
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = zf.read(metadata_name).decode("utf-8")

    for rel_path in PUBLIC_CONFIGS:
        packaged_path = f"certfix/configs/{rel_path.removeprefix('configs/')}"
        results.append(
            CheckResult(
                f"wheel contains {packaged_path}",
                packaged_path in names,
                "" if packaged_path in names else f"missing from {wheel}",
            )
        )

    mandatory_requires = [
        line.removeprefix("Requires-Dist: ")
        for line in metadata.splitlines()
        if line.startswith("Requires-Dist: ") and "; extra ==" not in line
    ]
    metadata_lines = set(metadata.splitlines())
    requires_lines = {line for line in metadata_lines if line.startswith("Requires-Dist: ")}
    results.append(
        CheckResult(
            "wheel mandatory dependencies are lightweight",
            mandatory_requires
            == ["click>=8.0.0", "httpx>=0.25.0", "pyyaml>=6.0", "rich>=13.0.0"],
            f"mandatory={mandatory_requires}",
        )
    )
    results.append(
        CheckResult(
            "wheel does not expose llama-cpp-python",
            not any("llama-cpp-python" in line for line in requires_lines),
        )
    )
    results.append(
        CheckResult(
            "wheel includes httpx in the base install",
            "Requires-Dist: httpx>=0.25.0" in metadata_lines
            and not any("extra == 'api'" in line for line in requires_lines),
        )
    )
    results.append(
        CheckResult(
            "wheel contains CERT-C rule metadata",
            "certfix/data/cert_c_rules_with_examples.json" in names,
        )
    )
    results.append(
        CheckResult(
            "wheel contains third-party notices",
            "certfix/THIRD_PARTY_NOTICES.md" in names,
        )
    )
    for rel_path in EXCLUDED_SAMPLE_DATA:
        packaged_path = rel_path.removeprefix("src/")
        results.append(
            CheckResult(
                f"wheel excludes {packaged_path}",
                packaged_path not in names,
            )
        )
    return results


def check_sdist(sdist: Path) -> list[CheckResult]:
    results: list[CheckResult] = [CheckResult("sdist exists", True, str(sdist))]
    with tarfile.open(sdist, "r:gz") as tf:
        names = {member.name for member in tf.getmembers()}

    for rel_path in EXCLUDED_PUBLIC_PATHS:
        included = any(
            _sdist_member_relpath(name) == rel_path
            or _sdist_member_relpath(name).startswith(f"{rel_path}/")
            for name in names
        )
        results.append(
            CheckResult(
                f"sdist excludes {rel_path}",
                not included,
            )
        )
    return results


def _sdist_member_relpath(name: str) -> str:
    parts = name.split("/", 1)
    return parts[1] if len(parts) == 2 else name


def check_git_clean_or_known_dirty() -> CheckResult:
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    dirty_lines = [
        line
        for line in completed.stdout.splitlines()
        if not line.endswith("scripts/check_release_readiness.py")
    ]
    return CheckResult(
        "git status has no unexpected dirty files",
        completed.returncode == 0 and not dirty_lines,
        "\n".join(dirty_lines),
    )


if __name__ == "__main__":
    raise SystemExit(main())
