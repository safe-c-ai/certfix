from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from certfix.docker_wrapper import main


def _completed(returncode: int) -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode)


def _command_args(calls) -> list[list[str]]:
    return [call.args[0] for call in calls]


def test_api_check_generates_profile_then_runs_doctor_and_check(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    config_path = tmp_path / "certfix.yaml"
    input_dir.mkdir()

    runner = CliRunner()
    with patch(
        "certfix.docker_wrapper.subprocess.run",
        side_effect=[_completed(0), _completed(0), _completed(1)],
    ) as run:
        result = runner.invoke(
            main,
            [
                "api-check",
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--config",
                str(config_path),
            ],
        )

    assert result.exit_code == 1
    assert output_dir.is_dir()
    commands = _command_args(run.call_args_list)
    assert commands[0][-5:] == [
        "config",
        "deepseek-v4-flash-openrouter",
        "--output",
        str(config_path),
        "--force",
    ]
    assert commands[1][-3:] == ["doctor", "--config", str(config_path)]
    assert commands[2][-6:] == [
        "check",
        str(input_dir),
        "--config",
        str(config_path),
        "--output-dir",
        str(output_dir),
    ]


def test_comment_merge_options_are_fix_only() -> None:
    runner = CliRunner()

    check_help = runner.invoke(main, ["api-check", "--help"])
    fix_help = runner.invoke(main, ["api-fix", "--help"])

    assert check_help.exit_code == 0
    assert "--comment-merge" not in check_help.output
    assert fix_help.exit_code == 0
    assert "--comment-merge" in fix_help.output
    assert "--comment-merge-audit" in fix_help.output


def test_api_fix_continues_after_check_finds_violations(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    config_path = tmp_path / "certfix.yaml"
    input_dir.mkdir()

    runner = CliRunner()
    with patch(
        "certfix.docker_wrapper.subprocess.run",
        side_effect=[_completed(0), _completed(0), _completed(1), _completed(0)],
    ) as run:
        result = runner.invoke(
            main,
            [
                "api-fix",
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--config",
                str(config_path),
            ],
        )

    assert result.exit_code == 0
    commands = _command_args(run.call_args_list)
    assert commands[2][-6:] == [
        "check",
        str(input_dir),
        "--config",
        str(config_path),
        "--output-dir",
        str(output_dir),
    ]
    assert commands[3][-6:] == [
        "fix",
        str(input_dir),
        "--config",
        str(config_path),
        "--output-dir",
        str(output_dir),
    ]


def test_api_fix_passes_comment_merge_options(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    config_path = tmp_path / "certfix.yaml"
    input_dir.mkdir()

    runner = CliRunner()
    with patch(
        "certfix.docker_wrapper.subprocess.run",
        side_effect=[_completed(0), _completed(0), _completed(1), _completed(0)],
    ) as run:
        result = runner.invoke(
            main,
            [
                "api-fix",
                "--comment-merge-audit",
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--config",
                str(config_path),
            ],
        )

    assert result.exit_code == 0
    fix_command = _command_args(run.call_args_list)[3]
    assert "--comment-merge" in fix_command
    assert "--comment-merge-audit" in fix_command


def test_local_fix_uses_docker_qwen_profile(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    config_path = tmp_path / "certfix.yaml"
    input_dir.mkdir()

    runner = CliRunner()
    with patch(
        "certfix.docker_wrapper.subprocess.run",
        side_effect=[_completed(0), _completed(0), _completed(0), _completed(0)],
    ) as run:
        result = runner.invoke(
            main,
            [
                "local-fix",
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--config",
                str(config_path),
            ],
        )

    assert result.exit_code == 0
    commands = _command_args(run.call_args_list)
    assert commands[0][-5:] == [
        "config",
        "qwen36-mtp-docker",
        "--output",
        str(config_path),
        "--force",
    ]


def test_fix_aborts_when_check_has_runtime_error(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    config_path = tmp_path / "certfix.yaml"
    input_dir.mkdir()

    runner = CliRunner()
    with patch(
        "certfix.docker_wrapper.subprocess.run",
        side_effect=[_completed(0), _completed(0), _completed(2)],
    ) as run:
        result = runner.invoke(
            main,
            [
                "local-fix",
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--config",
                str(config_path),
            ],
        )

    assert result.exit_code == 2
    assert len(run.call_args_list) == 3


def test_missing_input_path_fails_before_running_certfix(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch("certfix.docker_wrapper.subprocess.run") as run:
        result = runner.invoke(
            main,
            [
                "api-check",
                "--input",
                str(tmp_path / "missing"),
                "--output",
                str(tmp_path / "output"),
            ],
        )

    assert result.exit_code == 1
    assert "input path does not exist" in result.output
    run.assert_not_called()
