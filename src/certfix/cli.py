"""CLI entry point for certfix."""

from __future__ import annotations

import io
import json
import sys
import time
import traceback
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import click
from rich.console import Console

from certfix import __version__
from certfix.config import Config, RoleModelConfig
from certfix.env import load_dotenv
from certfix.exceptions import CertfixError, ModelNotFoundError
from certfix.inference.base import InferenceBackend
from certfix.models import (
    CheckResult,
    FixResult,
    Violation,
)

_DEFAULT_OUTPUT_DIR_NAME = "certfix-output"


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """certfix - CERT-C issue candidate detector and fixed-code candidate generator."""
    load_dotenv()


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--config", "config_path", type=click.Path(), default=None, help="Config file path")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "sarif"]),
    default="text",
)
@click.option("--rule", multiple=True, help="Check specific rules only")
@click.option("--threads", "-t", type=int, default=None, help="Number of CPU threads")
@click.option("--timeout", type=int, default=300, help="Inference timeout in seconds")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    help="Write check reports to this directory",
)
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode")
@click.option("--verbose", "-v", is_flag=True, help="Verbose mode")
def check(
    path: str,
    config_path: str | None,
    output_format: str,
    rule: tuple[str, ...],
    threads: int | None,
    timeout: int,
    output_dir: str | None,
    quiet: bool,
    verbose: bool,
) -> None:
    """Check for CERT-C violations in C source files."""
    stderr = Console(stderr=True, quiet=quiet or output_format in ("json", "sarif"))

    try:
        # Load config
        cfg = Config.load(Path(config_path) if config_path else None)

        # Build backend
        from certfix.inference.factory import create_detection_backend

        backend = create_detection_backend(cfg, threads=threads, timeout=timeout)

        if not backend.is_available():
            stderr.print(
                "[red]Error:[/red] Detection model not available. "
                "Run 'certfix doctor' and check your config."
            )
            sys.exit(2)

        # Build detector
        from certfix.core import Detector
        from certfix.core.include_resolver import IncludeResolver

        include_resolver = IncludeResolver(
            include_dirs=cfg.detection.include_dirs,
        )
        detector = Detector(backend, include_resolver=include_resolver)

        target = Path(path)
        rules = list(rule) if rule else None

        if _can_run_qwen36_batch_check(backend, cfg):
            if target.is_file():
                stderr.print(f"Checking {target}...")
            else:
                stderr.print(f"Scanning directory {target}...")
            result = _run_qwen36_batch_check(backend, target, rules, cfg)
            if not target.is_file():
                stderr.print(f"Checked {result.files_checked} files.")
        elif target.is_file():
            stderr.print(f"Checking {target}...")
            violations = detector.check_file(target, rules)
            result = CheckResult(files_checked=1, violations=violations)
        else:
            stderr.print(f"Scanning directory {target}...")
            result = detector.check_directory(target, rules, cfg.check.exclude or None)
            stderr.print(f"Checked {result.files_checked} files.")

        artifacts_dir = _resolve_output_dir(target, Path(output_dir) if output_dir else None)
        _write_check_artifacts(result, artifacts_dir)
        if not quiet and output_format == "text":
            stderr.print(f"Check reports written to {artifacts_dir / 'reports'}")

        # Output results
        from certfix.output import get_formatter

        output_buf = io.StringIO()
        formatter = get_formatter(output_format, output_buf)
        formatter.format_violations(result)
        click.echo(output_buf.getvalue(), nl=False)

        if result.has_violations:
            sys.exit(1)
        else:
            if not quiet:
                stderr.print("[green]No violations found.[/green]")
            sys.exit(0)

    except ModelNotFoundError:
        stderr.print(
            "[red]Error:[/red] Model not found. Run 'certfix doctor' and check your config."
        )
        if verbose:
            stderr.print(traceback.format_exc())
        sys.exit(2)
    except CertfixError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        if verbose:
            stderr.print(traceback.format_exc())
        sys.exit(2)
    except Exception as e:
        stderr.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            stderr.print(traceback.format_exc())
        sys.exit(2)


def _can_run_qwen36_batch_check(backend: InferenceBackend, cfg: Config) -> bool:
    """Return whether `certfix check` should use Qwen3.6 whole-file batching."""
    return (
        cfg.detection.backend in {"api", "local_llama_server"}
        and cfg.detection.prompt_profile == "qwen36_certfix_check_v1"
        and callable(getattr(backend, "detect_qwen36_batch", None))
    )


def _run_qwen36_batch_check(
    backend: InferenceBackend,
    target: Path,
    rules: list[str] | None,
    cfg: Config,
) -> CheckResult:
    """Run whole-file batched Qwen3.6 check."""
    files = _collect_check_files(target, cfg.check.exclude or None)
    if not files:
        return CheckResult(files_checked=0, violations=[])

    items = [(str(index), path.read_text(encoding="utf-8")) for index, path in enumerate(files)]
    batch_detect = backend.detect_qwen36_batch  # type: ignore[attr-defined]
    batch_results = batch_detect(items, rules=rules, batch_size=cfg.detection.batch_size)

    violations: list[Violation] = []
    for index, path in enumerate(files):
        for violation in batch_results.get(str(index), []):
            violation.file_path = str(path)
            violation.line = max(1, violation.line)
            violations.append(violation)

    return CheckResult(files_checked=len(files), violations=violations)


def _collect_check_files(target: Path, exclude: list[str] | None = None) -> list[Path]:
    exclude = [*(exclude or []), _DEFAULT_OUTPUT_DIR_NAME]
    if target.is_file():
        return [target]
    return [
        path
        for path in sorted(target.rglob("*.[ch]"))
        if not any(pattern in str(path) for pattern in exclude)
    ]


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--config", "config_path", type=click.Path(), default=None, help="Config file path")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "sarif"]),
    default="text",
)
@click.option("--rule", multiple=True, help="Fix specific rules only")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    help="Write fixed files and reports to this directory",
)
@click.option("--verify", is_flag=True, help="Verify fixes with compiler")
@click.option("--cflags", help="Compiler flags for verification")
@click.option("--threads", "-t", type=int, default=None, help="Number of CPU threads")
@click.option("--timeout", type=int, default=300, help="Inference timeout in seconds")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode")
@click.option("--verbose", "-v", is_flag=True, help="Verbose mode")
def fix(
    path: str,
    config_path: str | None,
    output_format: str,
    rule: tuple[str, ...],
    output_dir: str | None,
    verify: bool,
    cflags: str | None,
    threads: int | None,
    timeout: int,
    quiet: bool,
    verbose: bool,
) -> None:
    """Generate fixed-code candidates for CERT-C issue candidates in C source files."""
    if quiet and verbose:
        raise click.UsageError("--quiet and --verbose are mutually exclusive.")

    stderr = Console(stderr=True, quiet=quiet or output_format in ("json", "sarif"))

    try:
        # Load config
        cfg = Config.load(Path(config_path) if config_path else None)

        _run_simple_fix_command(
            path=Path(path),
            cfg=cfg,
            rules=list(rule) if rule else None,
            output_dir=Path(output_dir) if output_dir else None,
            output_format=output_format,
            verify=verify,
            cflags=cflags,
            threads=threads,
            timeout=timeout,
            stderr=stderr,
            quiet=quiet,
        )
        return

    except ModelNotFoundError:
        stderr.print(
            "[red]Error:[/red] Model not found. Run 'certfix doctor' and check your config."
        )
        if verbose:
            stderr.print(traceback.format_exc())
        sys.exit(2)
    except CertfixError as e:
        stderr.print(f"[red]Error:[/red] {e}")
        if verbose:
            stderr.print(traceback.format_exc())
        sys.exit(2)
    except Exception as e:
        stderr.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            stderr.print(traceback.format_exc())
        sys.exit(2)


CONFIG_PROFILES: dict[str, str] = {
    "qwen36-mtp-local": "qwen36-mtp-local.yaml",
    "qwen36-mtp-check": "qwen36-mtp-check.yaml",
    "deepseek-v4-flash-openrouter": "deepseek-v4-flash-openrouter.yaml",
    "deepseek-v4-flash-api": "deepseek-v4-flash-api.yaml",
    "gemini-3-flash-preview-openrouter": "gemini-3-flash-preview-openrouter.yaml",
    "local-detection-deepseek-fix": "examples/local-detection-deepseek-fix.yaml",
    "deepseek-gemini-step-overrides": "examples/deepseek-gemini-step-overrides.yaml",
}


@main.command("config")
@click.argument("profile", required=False)
@click.option("--list", "list_profiles", is_flag=True, help="List bundled config profiles")
@click.option("--output", "-o", type=click.Path(), default=None, help="Write profile to a file")
@click.option("--force", is_flag=True, help="Overwrite output file if it exists")
def config_command(
    profile: str | None,
    list_profiles: bool,
    output: str | None,
    force: bool,
) -> None:
    """List or write bundled config profiles."""
    console = Console(stderr=True)

    if list_profiles or profile is None:
        for name in CONFIG_PROFILES:
            click.echo(name)
        return

    if profile not in CONFIG_PROFILES:
        console.print(f"[red]Error:[/red] Unknown config profile: {profile}")
        console.print("Available profiles:")
        for name in CONFIG_PROFILES:
            console.print(f"  {name}")
        sys.exit(2)

    content = _read_bundled_config(profile)
    if output is None:
        click.echo(content, nl=False)
        return

    output_path = Path(output)
    if output_path.exists() and not force:
        console.print(f"[red]Error:[/red] Output file already exists: {output_path}")
        console.print("Use --force to overwrite it.")
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    console.print(f"Wrote {output_path}")


def _read_bundled_config(profile: str) -> str:
    """Read a bundled config profile by public profile name."""
    resource = resources.files("certfix.configs").joinpath(CONFIG_PROFILES[profile])
    return resource.read_text(encoding="utf-8")


def _run_simple_fix_command(
    path: Path,
    cfg: Config,
    rules: list[str] | None,
    output_dir: Path | None,
    output_format: str,
    verify: bool,
    cflags: str | None,
    threads: int | None,
    timeout: int,
    stderr: Console,
    quiet: bool,
) -> None:
    """Run the release-default fixed-code candidate generation path."""
    from certfix.core import Fixer
    from certfix.core.simple_repair import run_simple_repair
    from certfix.inference.factory import create_role_backend
    from certfix.output import get_formatter

    artifacts_dir = _resolve_output_dir(path, output_dir)
    role_name = cfg.step_role(
        "fix_generation",
        cfg.fix.simple_repairer_role or cfg.validation.semantic.reviewer_role,
    )
    role = cfg.models.get(role_name)
    if role is None:
        raise CertfixError(f"Simple repair role is not configured: {role_name}")

    backend = create_role_backend(role, threads=threads, timeout=timeout)
    if not backend.is_available():
        raise CertfixError(f"Simple repair model is not available: {role_name}")

    detection_backend: InferenceBackend | None = None
    detector = None
    if not rules and _simple_repair_profile_requires_rule(cfg.fix.simple_repair_profile):
        from certfix.core import Detector
        from certfix.core.include_resolver import IncludeResolver
        from certfix.inference.factory import create_detection_backend

        detection_backend = create_detection_backend(cfg, threads=threads, timeout=timeout)
        if not detection_backend.is_available():
            raise CertfixError(
                "Simple code-only repair requires an available detection model "
                "when --rule is not provided."
            )
        detector = Detector(
            detection_backend,
            include_resolver=IncludeResolver(include_dirs=cfg.detection.include_dirs),
        )

    files = _fix_target_files(path, cfg.check.exclude or None)
    if path.is_dir():
        stderr.print(f"Scanning directory {path}...")
        stderr.print(f"Checked {len(files)} files.")
    else:
        stderr.print(f"Checking {path}...")

    fixes: list[FixResult] = []
    fixer = Fixer(backend)
    semantic_role_name = cfg.step_role("semantic_check", cfg.validation.semantic.reviewer_role)
    semantic_backend = _reuse_or_create_step_backend(
        cfg,
        step="semantic_check",
        default_role_name=semantic_role_name,
        primary_role_name=role_name,
        primary_backend=backend,
        threads=threads,
        timeout=timeout,
    )
    retry_backend = _reuse_or_create_step_backend(
        cfg,
        step="retry_generation",
        default_role_name=role_name,
        primary_role_name=role_name,
        primary_backend=backend,
        threads=threads,
        timeout=timeout,
    )
    violation_audit_backend = _reuse_or_create_step_backend(
        cfg,
        step="violation_audit",
        default_role_name=semantic_role_name,
        primary_role_name=role_name,
        primary_backend=backend,
        threads=threads,
        timeout=timeout,
    )
    post_fix_detection_backend = (
        _create_available_step_backend(
            cfg,
            "post_fix_detection",
            cfg.step_role("post_fix_detection"),
            threads,
            timeout,
        )
        or None
    )
    retry_semantic_role_name = cfg.step_role("retry_semantic_check", semantic_role_name)
    retry_semantic_backend = _reuse_or_create_step_backend(
        cfg,
        step="retry_semantic_check",
        default_role_name=retry_semantic_role_name,
        primary_role_name=semantic_role_name or "",
        primary_backend=semantic_backend,
        threads=threads,
        timeout=timeout,
    )
    retry_violation_audit_backend = _reuse_or_create_step_backend(
        cfg,
        step="retry_violation_audit",
        default_role_name=retry_semantic_role_name,
        primary_role_name=retry_semantic_role_name or "",
        primary_backend=retry_semantic_backend,
        threads=threads,
        timeout=timeout,
    )
    retry_post_fix_detection_backend = (
        _create_available_step_backend(
            cfg,
            "retry_post_fix_detection",
            cfg.step_role("retry_post_fix_detection"),
            threads,
            timeout,
        )
        or post_fix_detection_backend
    )
    try:
        for target in files:
            fix_item_started = time.perf_counter()
            code = target.read_text(encoding="utf-8")
            repair_rules = list(rules or [])
            if not repair_rules and detection_backend is not None and detector is not None:
                detect_started = time.perf_counter()
                repair_rules = _detect_rules_for_simple_code_only_repair(
                    target,
                    detection_backend,
                    detector,
                    cfg,
                )
                if not repair_rules:
                    continue

            repair_started = time.perf_counter()
            fix_result = run_simple_repair(
                code=code,
                file_path=str(target),
                backend=backend,
                rules=repair_rules,
                max_tokens=cfg.fix.simple_max_tokens,
                prompt_profile=cfg.fix.simple_repair_profile,
            )
            simple_repair_seconds = time.perf_counter() - repair_started
            if fix_result is None:
                continue

            fix_result.source = "primary"
            if detection_backend is not None:
                fix_result.timings["simple_detection_seconds"] = (
                    time.perf_counter() - detect_started
                )
            fix_result.timings["simple_repair_seconds"] = simple_repair_seconds

            if verify and fix_result.success and not fixer.verify_fix(fix_result, cflags):
                fix_result.success = False
                fix_result.error_message = "Verification failed"

            if _is_v2_fix_validation_enabled(cfg) and fix_result.success:
                _validate_v2_fix(
                    fix_result,
                    semantic_backend,
                    cfg,
                    violation_backend=post_fix_detection_backend,
                    violation_audit_backend=violation_audit_backend,
                    release_semantic_backend=False,
                )
                fix_result = _maybe_run_validate_guided_retry(
                    fix_result,
                    retry_backend,
                    cfg,
                    validation_backend=semantic_backend,
                    violation_backend=post_fix_detection_backend,
                    violation_audit_backend=violation_audit_backend,
                    retry_validation_backend=retry_semantic_backend,
                    retry_violation_backend=retry_post_fix_detection_backend,
                    retry_violation_audit_backend=retry_violation_audit_backend,
                )

            fix_result.timings["fix_item_total_seconds"] = time.perf_counter() - fix_item_started
            fixes.append(fix_result)
    finally:
        _release_backends(
            retry_violation_audit_backend,
            retry_post_fix_detection_backend,
            retry_semantic_backend,
            violation_audit_backend,
            post_fix_detection_backend,
            detection_backend,
            retry_backend,
            semantic_backend,
            backend,
        )

    if not fixes:
        _write_fix_artifacts([], path, artifacts_dir)
        if not quiet and output_format == "text":
            stderr.print(f"Fix reports written to {artifacts_dir / 'reports'}")
        if not quiet:
            stderr.print("[green]No violations found.[/green]")
        sys.exit(0)

    _write_fix_artifacts(fixes, path, artifacts_dir)
    if not quiet and output_format == "text":
        stderr.print(f"Fix artifacts written to {artifacts_dir}")

    output_buf = io.StringIO()
    formatter = get_formatter(output_format, output_buf)
    formatter.format_fixes(fixes)
    click.echo(output_buf.getvalue(), nl=False)

    if any(not f.success for f in fixes):
        sys.exit(1)
    sys.exit(0)


def _fix_target_files(path: Path, exclude: list[str] | None) -> list[Path]:
    """Return C/C header files targeted by fix."""
    if path.is_file():
        return [path]

    excluded = [*(exclude or []), _DEFAULT_OUTPUT_DIR_NAME]
    return [
        c_file
        for c_file in sorted(path.rglob("*.[ch]"))
        if not any(pattern in str(c_file) for pattern in excluded)
    ]


def _resolve_output_dir(target: Path, output_dir: Path | None) -> Path:
    """Return the artifact output directory for check/fix commands."""
    if output_dir is not None:
        return output_dir
    base_dir = target if target.is_dir() else target.parent
    return base_dir / _DEFAULT_OUTPUT_DIR_NAME


def _write_check_artifacts(result: CheckResult, output_dir: Path) -> None:
    """Write check reports without changing source files."""
    from certfix.output import JsonFormatter, SarifFormatter

    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_buf = io.StringIO()
    JsonFormatter(json_buf).format_violations(result)
    (reports_dir / "check.json").write_text(json_buf.getvalue(), encoding="utf-8")

    sarif_buf = io.StringIO()
    SarifFormatter(sarif_buf).format_violations(result)
    (reports_dir / "check.sarif").write_text(sarif_buf.getvalue(), encoding="utf-8")

    summary = {
        "kind": "check",
        "files_checked": result.files_checked,
        "total_violations": result.total_violations,
    }
    (reports_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_fix_artifacts(fixes: list[FixResult], target: Path, output_dir: Path) -> None:
    """Write fixed candidates and reports without changing source files."""
    from certfix.output import JsonFormatter, SarifFormatter

    reports_dir = output_dir / "reports"
    fixes_dir = output_dir / "fixes"
    patches_dir = output_dir / "patches"
    reports_dir.mkdir(parents=True, exist_ok=True)
    fixes_dir.mkdir(parents=True, exist_ok=True)
    patches_dir.mkdir(parents=True, exist_ok=True)

    json_buf = io.StringIO()
    JsonFormatter(json_buf).format_fixes(fixes)
    (reports_dir / "fixes.json").write_text(json_buf.getvalue(), encoding="utf-8")

    sarif_buf = io.StringIO()
    SarifFormatter(sarif_buf).format_fixes(fixes)
    (reports_dir / "fixes.sarif").write_text(sarif_buf.getvalue(), encoding="utf-8")

    fixed_files: list[str] = []
    patch_files: list[str] = []
    base_dir = target if target.is_dir() else target.parent
    for fix in fixes:
        if not fix.success:
            continue
        source_path = Path(fix.violation.file_path)
        rel_source = _relative_artifact_source(source_path, base_dir)

        fixed_path = _fixed_artifact_path(fixes_dir, rel_source)
        fixed_path.parent.mkdir(parents=True, exist_ok=True)
        fixed_path.write_text(fix.fixed_code, encoding="utf-8")
        fixed_files.append(str(fixed_path))

        patch_path = _patch_artifact_path(patches_dir, rel_source)
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(fix.to_diff(), encoding="utf-8")
        patch_files.append(str(patch_path))

    summary = {
        "kind": "fix",
        "total": len(fixes),
        "successful": sum(1 for fix in fixes if fix.success),
        "failed": sum(1 for fix in fixes if not fix.success),
        "fixed_files": fixed_files,
        "patch_files": patch_files,
    }
    (reports_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )


def _relative_artifact_source(source_path: Path, base_dir: Path) -> Path:
    """Return a stable relative source path for artifact mirrors."""
    try:
        return source_path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        return Path(source_path.name)


def _fixed_artifact_path(root: Path, rel_source: Path) -> Path:
    """Return the fixed-code artifact path for a source-relative path."""
    suffix = rel_source.suffix
    fixed_name = f"{rel_source.stem}.fixed{suffix}" if suffix else f"{rel_source.name}.fixed"
    return root / rel_source.parent / fixed_name


def _patch_artifact_path(root: Path, rel_source: Path) -> Path:
    """Return the patch artifact path for a source-relative path."""
    return root / rel_source.parent / f"{rel_source.name}.patch"


def _is_v2_fix_validation_enabled(cfg: Config) -> bool:
    """Return whether fix should use v2 post-fix validation gates."""
    return bool(cfg.models)


def _simple_repair_profile_requires_rule(prompt_profile: str | None) -> bool:
    """Return whether the selected simple repair profile needs a target rule."""
    from certfix.prompt_profiles import RepairOutputMode, resolve_repair_profile

    return resolve_repair_profile(prompt_profile).output_mode == RepairOutputMode.CODE_ONLY


def _detect_rules_for_simple_code_only_repair(
    target: Path,
    backend: InferenceBackend,
    detector: Any,
    cfg: Config,
) -> list[str]:
    """Select target rule IDs before code-only simple repair."""
    if _can_run_qwen36_batch_check(backend, cfg):
        check_result = _run_qwen36_batch_check(backend, target, None, cfg)
        violations = check_result.violations
    else:
        violations = detector.check_file(target, None)

    rule_ids: list[str] = []
    for violation in violations:
        if violation.rule_id not in rule_ids:
            rule_ids.append(violation.rule_id)
    return rule_ids[:1]


def _release_backend(backend: InferenceBackend | None) -> None:
    """Release model memory between v2 pipeline stages when supported."""
    if backend is None:
        return

    close = getattr(backend, "close", None)
    if callable(close):
        close()

    try:
        import gc

        gc.collect()
    except Exception:
        pass


def _release_backends(*backends: InferenceBackend | None) -> None:
    """Release each backend once."""
    seen: set[int] = set()
    for backend in backends:
        if backend is None:
            continue
        backend_id = id(backend)
        if backend_id in seen:
            continue
        seen.add(backend_id)
        _release_backend(backend)


def _create_available_semantic_backend(
    cfg: Config,
    threads: int | None,
    timeout: int,
) -> InferenceBackend | None:
    """Create Stage 7 backend when v2 semantic validation is enabled."""
    if not _is_v2_fix_validation_enabled(cfg) or not cfg.validation.semantic.enabled:
        return None

    role_name = cfg.step_role("semantic_check", cfg.validation.semantic.reviewer_role)

    return _create_available_step_backend(
        cfg,
        "semantic_check",
        role_name,
        threads,
        timeout,
    )


def _create_available_step_backend(
    cfg: Config,
    step: str,
    default_role_name: str | None,
    threads: int | None,
    timeout: int,
) -> InferenceBackend | None:
    """Create a role backend for a specific pipeline step when configured."""
    role_name = cfg.step_role(step, default_role_name)
    if not role_name:
        return None
    role = cfg.models.get(role_name)
    if role is None:
        raise CertfixError(f"{step} role is not configured: {role_name}")

    from certfix.inference.factory import create_role_backend

    backend = create_role_backend(role, threads=threads, timeout=timeout)
    if not backend.is_available():
        raise CertfixError(f"{step} model is not available: {role_name}")
    return backend


def _reuse_or_create_step_backend(
    cfg: Config,
    *,
    step: str,
    default_role_name: str | None,
    primary_role_name: str,
    primary_backend: InferenceBackend,
    threads: int | None,
    timeout: int,
) -> InferenceBackend:
    """Reuse the primary backend when a step resolves to the same role."""
    role_name = cfg.step_role(step, default_role_name)
    if role_name == primary_role_name:
        return primary_backend
    return _create_available_step_backend(cfg, step, role_name, threads, timeout) or primary_backend


def _step_max_tokens(cfg: Config, step: str, default_role_name: str, default: int = 1024) -> int:
    """Return max tokens for the role serving a pipeline step."""
    role_name = cfg.step_role(step, default_role_name)
    role = cfg.models.get(role_name) if role_name else None
    return role.max_tokens if role and role.max_tokens is not None else default


def _validate_v2_fix(
    fix_result: FixResult,
    semantic_backend: InferenceBackend | None,
    cfg: Config,
    violation_backend: InferenceBackend | None = None,
    violation_audit_backend: InferenceBackend | None = None,
    release_semantic_backend: bool = True,
    semantic_step: str = "semantic_check",
) -> None:
    """Run SPEC-compatible release validation and update a fix result."""
    from certfix.core.fix_validator import validate_fix_result

    created_violation_backend: InferenceBackend | None = None
    violation_enabled = cfg.validation.violation_removal.enabled and (
        violation_backend is not None
        or (
            cfg.detection.backend == "api"
            and cfg.detection.prompt_profile == "qwen36_certfix_check_v1"
        )
    )
    try:
        if violation_enabled and violation_backend is None:
            from certfix.inference.factory import create_detection_backend

            created_violation_backend = create_detection_backend(cfg)
            violation_backend = created_violation_backend

        validation_started = time.perf_counter()
        validate_fix_result(
            fix_result,
            compile_config=cfg.validation.compile,
            semantic_backend=semantic_backend,
            semantic_max_tokens=_step_max_tokens(
                cfg,
                semantic_step,
                cfg.validation.semantic.reviewer_role,
            ),
            violation_backend=violation_backend,
            violation_audit_backend=violation_audit_backend or semantic_backend,
            compile_enabled=cfg.validation.compile.enabled,
            violation_removal_enabled=violation_enabled,
            semantic_enabled=cfg.validation.semantic.enabled,
            programmatic_preset="release_v1",
            violation_removal_method=cfg.validation.violation_removal.method,
            violation_removal_max_tokens=cfg.validation.violation_removal.max_tokens,
            violation_removal_override_denylist=(
                cfg.validation.violation_removal.override_denylist
            ),
        )
        fix_result.timings["validation_total_seconds"] = time.perf_counter() - validation_started
    finally:
        if created_violation_backend is not None:
            _release_backend(created_violation_backend)
        if release_semantic_backend:
            _release_backend(semantic_backend)


def _maybe_run_validate_guided_retry(
    primary_result: FixResult,
    backend: InferenceBackend,
    cfg: Config,
    validation_backend: InferenceBackend | None = None,
    violation_backend: InferenceBackend | None = None,
    violation_audit_backend: InferenceBackend | None = None,
    retry_validation_backend: InferenceBackend | None = None,
    retry_violation_backend: InferenceBackend | None = None,
    retry_violation_audit_backend: InferenceBackend | None = None,
) -> FixResult:
    """Run one validate-guided retry for a failed primary simple repair."""
    if (
        primary_result.success
        or not cfg.fix.validate_guided_retry
        or cfg.fix.retry_max_attempts <= 0
    ):
        primary_result.retry_metadata.setdefault(
            "selected_source",
            "primary_pass" if primary_result.success else "primary_rejected",
        )
        return primary_result

    from certfix.core.validate_guided_retry import (
        classify_retry_failure,
        run_validate_guided_retry,
    )

    failure = classify_retry_failure(primary_result)
    primary_result.retry_metadata.update(
        {
            "failure_category": failure.category,
            "failure_detail": failure.detail,
            "retryable": failure.retryable,
        }
    )
    if not failure.retryable:
        return primary_result

    retry_started = time.perf_counter()
    retry_result = run_validate_guided_retry(
        primary=primary_result,
        backend=backend,
        max_tokens=cfg.fix.retry_max_tokens,
        use_rule_addenda_v1=cfg.fix.retry_rule_addenda_v1,
        enabled_rule_addenda=cfg.fix.retry_rule_addenda_rule_ids,
    )
    primary_result.timings["retry_generation_seconds"] = time.perf_counter() - retry_started
    if retry_result is None:
        primary_result.retry_metadata["retry_error"] = "retry generation produced no code"
        return primary_result

    retry_result.timings.update(primary_result.timings)
    retry_result.timings["retry_generation_seconds"] = time.perf_counter() - retry_started
    _validate_v2_fix(
        retry_result,
        retry_validation_backend or validation_backend or backend,
        cfg,
        violation_backend=retry_violation_backend or violation_backend,
        violation_audit_backend=retry_violation_audit_backend or violation_audit_backend,
        release_semantic_backend=False,
        semantic_step="retry_semantic_check",
    )

    primary_result.retry_metadata["retry_status"] = (
        retry_result.final_status.value if retry_result.final_status else None
    )
    primary_result.retry_metadata["retry_success"] = retry_result.success
    primary_result.retry_metadata["rule_addendum_id"] = retry_result.retry_metadata.get(
        "rule_addendum_id"
    )

    if retry_result.success:
        retry_result.retry_metadata["primary_status"] = (
            primary_result.final_status.value if primary_result.final_status else None
        )
        retry_result.retry_metadata["selected_source"] = "retry_pass"
        return retry_result

    primary_result.retry_metadata["selected_source"] = "primary_rejected"
    return primary_result


def _role_artifacts(role_name: str, role: RoleModelConfig) -> list[tuple[Path, str, bool, bool]]:
    """Return required local artifacts for a configured model role."""
    return []


def _create_role_dirs(cfg: Config) -> None:
    """Create local directories implied by role-based model config."""
    return None


def _print_role_model_status(console: Console, cfg: Config, verbose: bool) -> bool:
    """Print role-based model artifact status."""
    all_ok = True
    console.print("[bold]Model roles:[/bold]")
    for role_name, role in cfg.models.items():
        profile = f", {role.profile}" if role.profile else ""
        console.print(f"[bold]{role_name} ({role.backend}{profile}):[/bold]")

        artifacts = _role_artifacts(role_name, role)
        if not artifacts:
            console.print("  local files: not checked")
            console.print()
            continue

        for path, label, is_dir, check_non_empty in artifacts:
            if not _check_file_status(
                console,
                path,
                label,
                verbose,
                is_dir=is_dir,
                check_non_empty=check_non_empty,
            ):
                all_ok = False
        console.print()

    return all_ok


@main.command()
@click.option("--config", "config_path", type=click.Path(), default=None, help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Show details (absolute paths, file sizes)")
def setup(config_path: str | None, verbose: bool) -> None:
    """Show optional model-file diagnostics."""
    console = Console()

    try:
        cfg = Config.load(Path(config_path) if config_path else None)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to load config: {e}")
        sys.exit(2)

    # Create directories
    try:
        if cfg.models:
            _create_role_dirs(cfg)
        else:
            pass
    except OSError as e:
        console.print(f"[red]Error:[/red] Failed to create directory: {e}")
        sys.exit(2)

    console.print("[bold]certfix setup[/bold]")
    console.print()

    all_ok = True

    if cfg.models:
        all_ok = _print_role_model_status(console, cfg, verbose)
    else:
        console.print("No local model files are managed by certfix setup.")
        console.print("For local inference, start the configured OpenAI-compatible server.")
        console.print()

    if all_ok:
        console.print("[green]Ready to use.[/green]")
        sys.exit(0)

    console.print("[yellow]Some model files are missing.[/yellow]")
    sys.exit(1)


@main.command()
@click.option("--config", "config_path", type=click.Path(), default=None, help="Config file path")
def doctor(config_path: str | None) -> None:
    """Check environment and diagnose issues."""
    console = Console(highlight=False)
    all_ok = True

    console.print("[bold]certfix doctor[/bold]")
    console.print()

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    console.print(f"  Python:          {py_ver} [green]✓[/green]")

    # certfix version
    console.print(f"  certfix:         {__version__}")

    try:
        cfg = Config.load(Path(config_path) if config_path else None)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to load config: {e}")
        sys.exit(2)
    if cfg.models:
        if not _print_role_model_status(console, cfg, verbose=False):
            all_ok = False
    else:
        console.print("  Model layout:    no local role files configured")

    console.print()

    # Backend availability
    from certfix.inference.factory import create_detection_backend

    fix_role_name = _configured_simple_fix_role_name(cfg)
    fix_role = cfg.models.get(fix_role_name) if fix_role_name else None

    console.print(f"  Detection backend: {cfg.detection.backend}")
    if fix_role_name and fix_role:
        console.print(f"  Fix role:          {fix_role_name} ({fix_role.backend})")
    else:
        console.print(f"  Fix backend:       {cfg.model.backend}")
    if cfg.models:
        console.print(f"  Model roles:       {len(cfg.models)}")
    console.print()

    try:
        det_backend = create_detection_backend(cfg)
        if det_backend.is_available():
            console.print("  Detection ready: [green]Yes[/green]")
        else:
            console.print("  Detection ready: [red]No[/red]")
            all_ok = False
    except Exception as e:
        console.print(f"  Detection ready: [red]No[/red] ({e})")
        all_ok = False

    try:
        fix_backend = _create_doctor_fix_backend(cfg)
        if fix_backend.is_available():
            console.print("  Fix ready:       [green]Yes[/green]")
        else:
            console.print("  Fix ready:       [red]No[/red]")
            all_ok = False
    except Exception as e:
        console.print(f"  Fix ready:       [red]No[/red] ({e})")
        all_ok = False

    if not _print_local_llama_server_status(console, cfg):
        all_ok = False

    if not all_ok:
        console.print()
        console.print("[yellow]Some components are not available.[/yellow]")

    sys.exit(0)


def _configured_simple_fix_role_name(cfg: Config) -> str | None:
    """Return the configured simple repair role name for doctor output."""
    return cfg.step_role(
        "fix_generation",
        cfg.fix.simple_repairer_role or cfg.validation.semantic.reviewer_role,
    )


def _create_doctor_fix_backend(cfg: Config) -> InferenceBackend:
    """Create the backend that `certfix fix` will use when configured."""
    role_name = _configured_simple_fix_role_name(cfg)
    role = cfg.models.get(role_name) if role_name else None
    if role is not None:
        from certfix.inference.factory import create_role_backend

        return create_role_backend(role)

    from certfix.inference.factory import create_fix_backend

    return create_fix_backend(cfg)


def _print_local_llama_server_status(console: Console, cfg: Config) -> bool:
    """Print local llama-server reachability for local_llama_server configs."""
    targets = _configured_local_llama_servers(cfg)
    if not targets:
        return True

    all_reachable = True
    console.print()
    for label, base_url, model in targets:
        if _is_openai_server_reachable(base_url):
            console.print(f"  {label}: [green]reachable[/green] ({base_url})")
            continue

        all_reachable = False
        console.print(f"  {label}: [yellow]not reachable[/yellow] ({base_url})")
        console.print("  Start the local llama-server before running check/fix, for example:")
        console.print()
        console.print(_local_llama_server_start_command(base_url, model))
        console.print()
        console.print("  Then run `certfix doctor` again.")

    return all_reachable


def _configured_local_llama_servers(cfg: Config) -> list[tuple[str, str, str]]:
    """Return unique local llama-server targets configured for detection/roles."""
    targets: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(label: str, backend: str, api: Any) -> None:
        base_url = getattr(api, "base_url", "")
        model = getattr(api, "model", "")
        if backend != "local_llama_server" or not base_url:
            return
        key = base_url.rstrip("/")
        if key in seen:
            return
        seen.add(key)
        targets.append((label, base_url, model))

    add("Local llama-server", cfg.detection.backend, cfg.detection.api)
    for role_name, role in cfg.models.items():
        add(f"Local llama-server role `{role_name}`", role.backend, role.api)
    return targets


def _is_openai_server_reachable(base_url: str) -> bool:
    """Return whether an OpenAI-compatible server responds to /models."""
    try:
        import httpx

        response = httpx.get(f"{base_url.rstrip('/')}/models", timeout=1.0)
        return response.status_code < 500
    except Exception:
        return False


def _local_llama_server_start_command(base_url: str, model: str) -> str:
    """Build the recommended local Qwen3.6 llama-server command."""
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8952
    model_ref = model or "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL"
    return "\n".join(
        [
            "  llama-server \\",
            f"    -hf {model_ref} \\",
            "    -ngl 99 -c 8192 -fa on -np 1 \\",
            f"    --host {host} --port {port} \\",
            "    --cache-ram 0 \\",
            "    --spec-type draft-mtp --spec-draft-n-max 2 \\",
            "    --reasoning-budget 1024",
        ]
    )


def _print_package_status(console: Console, label: str, import_name: str) -> None:
    """Print package import status with version if available."""
    padded = f"{label}:".ljust(17)
    try:
        mod = __import__(import_name)
        version = getattr(mod, "__version__", "unknown")
        console.print(f"  {padded}{version} [green]✓[/green]")
    except (ImportError, Exception):
        console.print(f"  {padded}not installed [red]✗[/red]")


def _check_file_status(
    console: Console,
    path: Path,
    label: str,
    verbose: bool,
    is_dir: bool = False,
    check_non_empty: bool = False,
) -> bool:
    """Check and display file/directory status. Returns True if present."""
    if is_dir:
        exists = path.is_dir()
        if exists and check_non_empty:
            exists = any(path.iterdir())
    else:
        exists = path.is_file()

    if exists:
        status = "[green]OK[/green]"
        detail = ""
        if verbose:
            abs_path = path.resolve()
            if is_dir:
                count = sum(1 for _ in path.iterdir())
                detail = f" ({abs_path}, {count} files)"
            else:
                size_mb = path.stat().st_size / (1024 * 1024)
                detail = f" ({abs_path}, {size_mb:.1f} MB)"
        console.print(f"  {label}: {status}{detail}")
        return True
    else:
        status = "[red]Missing[/red]"
        detail = ""
        if verbose:
            detail = f" (expected: {path.resolve()})"
        console.print(f"  {label}: {status}{detail}")
        return False


if __name__ == "__main__":
    main()
