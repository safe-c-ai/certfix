"""Docker-first wrapper commands for certfix container usage."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

API_PROFILE = "deepseek-v4-flash-openrouter"
LOCAL_PROFILE = "qwen36-mtp-docker"
DEFAULT_INPUT = Path("/input")
DEFAULT_OUTPUT = Path("/output")
DEFAULT_CONFIG = Path("/tmp/certfix-docker.yaml")


def _run_certfix(args: list[str]) -> int:
    completed = subprocess.run([sys.executable, "-m", "certfix", *args], check=False)
    return int(completed.returncode)


def _prepare_paths(input_path: Path, output_dir: Path, config_path: Path) -> None:
    if not input_path.exists():
        raise click.ClickException(f"input path does not exist: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)


def _run_config(profile: str, config_path: Path) -> int:
    return _run_certfix(["config", profile, "--output", str(config_path), "--force"])


def _run_doctor(config_path: Path) -> int:
    return _run_certfix(["doctor", "--config", str(config_path)])


def _run_check(input_path: Path, output_dir: Path, config_path: Path) -> int:
    return _run_certfix(
        [
            "check",
            str(input_path),
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )


def _run_fix(
    input_path: Path,
    output_dir: Path,
    config_path: Path,
    *,
    comment_merge: bool,
    comment_merge_audit: bool,
) -> int:
    args = [
        "fix",
        str(input_path),
        "--config",
        str(config_path),
        "--output-dir",
        str(output_dir),
    ]
    if comment_merge:
        args.append("--comment-merge")
    if comment_merge_audit:
        args.append("--comment-merge-audit")
    return _run_certfix(args)


def _run_flow(
    *,
    profile: str,
    input_path: Path,
    output_dir: Path,
    config_path: Path,
    mode: str,
    skip_doctor: bool,
    comment_merge: bool,
    comment_merge_audit: bool,
) -> int:
    _prepare_paths(input_path, output_dir, config_path)

    config_exit = _run_config(profile, config_path)
    if config_exit != 0:
        return config_exit

    if not skip_doctor:
        doctor_exit = _run_doctor(config_path)
        if doctor_exit != 0:
            return doctor_exit

    check_exit = _run_check(input_path, output_dir, config_path)
    if mode == "check":
        return check_exit
    if check_exit == 2:
        return check_exit

    return _run_fix(
        input_path,
        output_dir,
        config_path,
        comment_merge=comment_merge or comment_merge_audit,
        comment_merge_audit=comment_merge_audit,
    )


def _common_options(default_profile: str, *, include_fix_options: bool = False):
    def decorator(command):
        command = click.option(
            "--skip-doctor",
            is_flag=True,
            help="Skip certfix doctor before running check/fix.",
        )(command)
        if include_fix_options:
            command = click.option(
                "--comment-merge-audit",
                is_flag=True,
                help="LLM-audit comment-merged artifacts before writing them.",
            )(command)
            command = click.option(
                "--comment-merge",
                is_flag=True,
                help="Write optional comment-merged fixed-code artifacts after validation.",
            )(command)
        command = click.option(
            "--config",
            "config_path",
            type=click.Path(path_type=Path, dir_okay=False),
            default=DEFAULT_CONFIG,
            show_default=True,
            help="Temporary generated certfix config path inside the container.",
        )(command)
        command = click.option(
            "--output",
            "output_dir",
            type=click.Path(path_type=Path, file_okay=False),
            default=DEFAULT_OUTPUT,
            show_default=True,
            help="Output directory for certfix reports, fixes, and patches.",
        )(command)
        command = click.option(
            "--input",
            "input_path",
            type=click.Path(path_type=Path),
            default=DEFAULT_INPUT,
            show_default=True,
            help="Input C source file or directory.",
        )(command)
        command = click.option(
            "--profile",
            default=default_profile,
            show_default=True,
            help="Bundled certfix config profile to generate.",
        )(command)
        return command

    return decorator


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Run certfix inside Docker with standard /input and /output mounts."""


@main.command("api-check")
@_common_options(API_PROFILE)
def api_check(
    profile: str,
    input_path: Path,
    output_dir: Path,
    config_path: Path,
    skip_doctor: bool,
) -> None:
    """Generate an API profile and run certfix check."""
    raise SystemExit(
        _run_flow(
            profile=profile,
            input_path=input_path,
            output_dir=output_dir,
            config_path=config_path,
            mode="check",
            skip_doctor=skip_doctor,
            comment_merge=False,
            comment_merge_audit=False,
        )
    )


@main.command("api-fix")
@_common_options(API_PROFILE, include_fix_options=True)
def api_fix(
    profile: str,
    input_path: Path,
    output_dir: Path,
    config_path: Path,
    skip_doctor: bool,
    comment_merge: bool,
    comment_merge_audit: bool,
) -> None:
    """Generate an API profile and run certfix check followed by fix."""
    raise SystemExit(
        _run_flow(
            profile=profile,
            input_path=input_path,
            output_dir=output_dir,
            config_path=config_path,
            mode="fix",
            skip_doctor=skip_doctor,
            comment_merge=comment_merge,
            comment_merge_audit=comment_merge_audit,
        )
    )


@main.command("local-check")
@_common_options(LOCAL_PROFILE)
def local_check(
    profile: str,
    input_path: Path,
    output_dir: Path,
    config_path: Path,
    skip_doctor: bool,
) -> None:
    """Generate the Docker local Qwen profile and run certfix check."""
    raise SystemExit(
        _run_flow(
            profile=profile,
            input_path=input_path,
            output_dir=output_dir,
            config_path=config_path,
            mode="check",
            skip_doctor=skip_doctor,
            comment_merge=False,
            comment_merge_audit=False,
        )
    )


@main.command("local-fix")
@_common_options(LOCAL_PROFILE, include_fix_options=True)
def local_fix(
    profile: str,
    input_path: Path,
    output_dir: Path,
    config_path: Path,
    skip_doctor: bool,
    comment_merge: bool,
    comment_merge_audit: bool,
) -> None:
    """Generate the Docker local Qwen profile and run check followed by fix."""
    raise SystemExit(
        _run_flow(
            profile=profile,
            input_path=input_path,
            output_dir=output_dir,
            config_path=config_path,
            mode="fix",
            skip_doctor=skip_doctor,
            comment_merge=comment_merge,
            comment_merge_audit=comment_merge_audit,
        )
    )


if __name__ == "__main__":
    main()
