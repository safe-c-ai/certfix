"""Integration tests for CLI."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from certfix.cli import main
from certfix.config import ApiConfig, Config, DetectionModelConfig, RoleModelConfig
from certfix.models import (
    CheckResult,
    CompileCheckResult,
    FinalFixStatus,
    SemanticAutoApplyResult,
    Severity,
    Violation,
)

_PATCH_DET_FACTORY = "certfix.inference.factory.create_detection_backend"
_PATCH_ROLE_BACKEND_FACTORY = "certfix.inference.factory.create_role_backend"
_PATCH_DETECTOR = "certfix.core.Detector"
_PATCH_CONFIG_LOAD = "certfix.cli.Config.load"


def _mock_det_backend(available: bool = True) -> MagicMock:
    """Create a mock detection backend."""
    backend = MagicMock()
    backend.is_available.return_value = available
    return backend


def _mock_fix_backend(available: bool = True) -> MagicMock:
    """Create a mock fix backend."""
    backend = MagicMock()
    backend.is_available.return_value = available
    return backend


class TestCLI:
    """Tests for CLI commands."""

    def test_version(self) -> None:
        """Test --version option."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "0.1.1" in result.output

    def test_help(self) -> None:
        """Test --help option."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "certfix" in result.output
        assert "check" in result.output
        assert "fix" in result.output

    def test_check_help(self) -> None:
        """Test check --help."""
        runner = CliRunner()
        result = runner.invoke(main, ["check", "--help"])

        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--rule" in result.output
        assert "--config" in result.output
        assert "--output-dir" in result.output

    def test_fix_help(self) -> None:
        """Test fix --help."""
        runner = CliRunner()
        result = runner.invoke(main, ["fix", "--help"])

        assert result.exit_code == 0
        assert "--output-dir" in result.output
        assert "--apply" not in result.output
        assert "--interactive" not in result.output
        assert "--verify" in result.output
        assert "--mode" not in result.output

class TestCheckCommand:
    """Tests for the check command."""

    def test_check_sarif_output(self, tmp_path: Path) -> None:
        """--format sarif should produce valid SARIF 2.1.0 JSON."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text("int x;")

        violation = Violation(
            rule_id="EXP33-C",
            file_path=str(c_file),
            line=1,
            column=1,
            message="CERT-C EXP33-C: Do not read uninitialized memory",
            severity=Severity.ERROR,
        )

        runner = CliRunner()
        with (
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend()),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.check_file.return_value = [violation]
            mock_det_cls.return_value = mock_detector

            result = runner.invoke(main, ["check", "--format", "sarif", str(c_file)])

        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"
        assert len(data["runs"]) == 1
        assert data["runs"][0]["results"][0]["ruleId"] == "EXP33-C"
        assert len(data["runs"][0]["tool"]["driver"]["rules"]) == 1

    def test_check_no_backend(self, tmp_path: Path) -> None:
        """Backend unavailable should exit 2."""
        c_file = tmp_path / "test.c"
        c_file.write_text("int main() { return 0; }")

        runner = CliRunner()
        with patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend(False)):
            result = runner.invoke(main, ["check", str(c_file)])

        assert result.exit_code == 2

    def test_check_c_file_mock(self, tmp_path: Path) -> None:
        """Check a C file with mock violation detected."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text('char *p = malloc(10);\nfree(p);\nprintf("%s", p);\n')

        violation = Violation(
            rule_id="MEM30-C",
            file_path=str(c_file),
            line=3,
            column=1,
            message="CERT-C MEM30-C: Do not access freed memory",
            severity=Severity.ERROR,
        )

        runner = CliRunner()
        with (
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend()),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.check_file.return_value = [violation]
            mock_det_cls.return_value = mock_detector

            result = runner.invoke(main, ["check", str(c_file)])

        assert result.exit_code == 1
        assert "MEM30-C" in result.output
        assert (tmp_path / "certfix-output" / "reports" / "check.json").exists()
        assert (tmp_path / "certfix-output" / "reports" / "check.sarif").exists()

    def test_check_c_file_no_violation_mock(self, tmp_path: Path) -> None:
        """No violations should exit 0."""
        c_file = tmp_path / "clean.c"
        c_file.write_text("int main() { return 0; }")

        runner = CliRunner()
        with (
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend()),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.check_file.return_value = []
            mock_det_cls.return_value = mock_detector

            result = runner.invoke(main, ["check", str(c_file)])

        assert result.exit_code == 0

    def test_check_json_output_mock(self, tmp_path: Path) -> None:
        """JSON output should have correct structure."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text("int x;")

        violation = Violation(
            rule_id="EXP33-C",
            file_path=str(c_file),
            line=1,
            column=1,
            message="CERT-C EXP33-C: Do not read uninitialized memory",
            severity=Severity.ERROR,
        )

        runner = CliRunner()
        with (
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend()),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.check_file.return_value = [violation]
            mock_det_cls.return_value = mock_detector

            result = runner.invoke(main, ["check", "--format", "json", str(c_file)])

        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["tool"] == "certfix"
        assert data["summary"]["total_violations"] == 1
        assert len(data["files"]) == 1

    def test_check_quiet_mode(self, tmp_path: Path) -> None:
        """Quiet mode should suppress progress output."""
        c_file = tmp_path / "clean.c"
        c_file.write_text("int main() { return 0; }")

        runner = CliRunner()
        with (
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend()),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.check_file.return_value = []
            mock_det_cls.return_value = mock_detector

            result = runner.invoke(main, ["check", "--quiet", str(c_file)])

        assert result.exit_code == 0

    def test_check_rule_filter(self, tmp_path: Path) -> None:
        """Rule filter should be passed to detector."""
        c_file = tmp_path / "test.c"
        c_file.write_text("int main() { return 0; }")

        runner = CliRunner()
        with (
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend()),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.check_file.return_value = []
            mock_det_cls.return_value = mock_detector

            result = runner.invoke(main, ["check", "--rule", "EXP33-C", str(c_file)])

        assert result.exit_code == 0
        mock_detector.check_file.assert_called_once()
        call_args = mock_detector.check_file.call_args
        assert call_args[0][1] == ["EXP33-C"]

    def test_check_directory_mock(self, tmp_path: Path) -> None:
        """Directory scan should use check_directory."""
        (tmp_path / "a.c").write_text("int x;")
        (tmp_path / "b.c").write_text("int y;")

        check_result = CheckResult(files_checked=2, violations=[])

        runner = CliRunner()
        with (
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend()),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.check_directory.return_value = check_result
            mock_det_cls.return_value = mock_detector

            result = runner.invoke(main, ["check", str(tmp_path)])

        assert result.exit_code == 0
        mock_detector.check_directory.assert_called_once()

    def test_check_qwen36_profile_uses_batch_path(self, tmp_path: Path) -> None:
        """Qwen3.6 check profile should use whole-file batch detection."""
        a_file = tmp_path / "a.c"
        b_file = tmp_path / "b.c"
        a_file.write_text("int x;")
        b_file.write_text("int y;")

        violation = Violation(
            rule_id="ARR30-C",
            file_path="",
            line=1,
            column=1,
            message="batched finding",
            severity=Severity.ERROR,
        )
        backend = _mock_det_backend()
        backend.detect_qwen36_batch.return_value = {"0": [violation], "1": []}
        cfg = Config(
            detection=DetectionModelConfig(
                backend="api",
                prompt_profile="qwen36_certfix_check_v1",
                batch_size=2,
            )
        )

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_DET_FACTORY, return_value=backend),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            result = runner.invoke(main, ["check", "--format", "json", str(tmp_path)])

        assert result.exit_code == 1
        backend.detect_qwen36_batch.assert_called_once()
        _items, kwargs = backend.detect_qwen36_batch.call_args
        assert kwargs["batch_size"] == 2
        mock_det_cls.return_value.check_directory.assert_not_called()

        data = json.loads(result.output)
        files = data["files"]
        assert files[0]["path"] == str(a_file)
        assert files[0]["violations"][0]["rule_id"] == "ARR30-C"

    def test_check_qwen36_local_profile_uses_batch_path(self, tmp_path: Path) -> None:
        """Local Qwen3.6 check profile should use whole-file batch detection."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text("int x;\n")

        violation = Violation(
            rule_id="EXP33-C",
            file_path="",
            line=1,
            column=1,
            message="batched local finding",
            severity=Severity.ERROR,
        )
        backend = _mock_det_backend()
        backend.detect_qwen36_batch.return_value = {"0": [violation]}
        cfg = Config(
            detection=DetectionModelConfig(
                backend="local_llama_server",
                prompt_profile="qwen36_certfix_check_v1",
                batch_size=1,
            )
        )

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_DET_FACTORY, return_value=backend),
            patch(_PATCH_DETECTOR) as mock_det_cls,
        ):
            result = runner.invoke(main, ["check", "--format", "json", str(c_file)])

        assert result.exit_code == 1
        backend.detect_qwen36_batch.assert_called_once()
        mock_det_cls.return_value.check_file.assert_not_called()

    def test_check_qwen36_local_batch_failure_exits_2(self, tmp_path: Path) -> None:
        """Local Qwen3.6 runtime failures must not report a false clean result."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text("int x;\n")

        backend = _mock_det_backend()
        backend.detect_qwen36_batch.side_effect = RuntimeError("server unreachable")
        cfg = Config(
            detection=DetectionModelConfig(
                backend="local_llama_server",
                prompt_profile="qwen36_certfix_check_v1",
                batch_size=1,
            )
        )

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_DET_FACTORY, return_value=backend),
        ):
            result = runner.invoke(main, ["check", str(c_file)])

        assert result.exit_code == 2
        assert "server unreachable" in result.output
        assert "No violations found" not in result.output

class TestDoctorCommand:
    """Tests for the doctor command."""

    def test_doctor_runs(self) -> None:
        """Doctor should run without errors."""
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0
        assert "certfix doctor" in result.output

    def test_doctor_shows_versions(self) -> None:
        """Doctor should show Python and certfix versions."""
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0
        assert "Python:" in result.output
        assert "certfix:" in result.output
        assert "0.1.1" in result.output

    def test_doctor_omits_removed_llama_cpp_status(self) -> None:
        """Doctor should not advertise the removed in-process llama.cpp backend."""
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0
        assert "llama-cpp:" not in result.output

    def test_doctor_shows_backend_status(self) -> None:
        """Doctor should show backend readiness."""
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0
        assert "Detection ready:" in result.output
        assert "Fix ready:" in result.output

    def test_doctor_shows_backend_type(self) -> None:
        """Doctor should show configured backend types."""
        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0
        assert "Detection backend:" in result.output
        assert "Fix backend:" in result.output

    def test_doctor_shows_role_models(self, tmp_path: Path) -> None:
        """Doctor should show role-based model status when models are configured."""
        cfg = _make_role_setup_config(tmp_path)

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend(available=False)),
            patch(_PATCH_ROLE_BACKEND_FACTORY, return_value=_mock_fix_backend(available=False)),
        ):
            result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0
        assert "Model roles:" in result.output
        assert "qwen36_local" in result.output
        assert "Model roles:       1" in result.output

    def test_doctor_custom_config(self, tmp_path: Path) -> None:
        """--config should be passed to Config.load."""
        cfg = _make_role_setup_config(tmp_path)
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("")

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg) as mock_load,
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend(available=False)),
            patch(_PATCH_ROLE_BACKEND_FACTORY, return_value=_mock_fix_backend(available=False)),
        ):
            result = runner.invoke(main, ["doctor", "--config", str(config_file)])

        mock_load.assert_called_once_with(Path(str(config_file)))
        assert result.exit_code == 0

    def test_doctor_warns_when_local_llama_server_is_not_reachable(self, tmp_path: Path) -> None:
        """Doctor should show the start command when local llama-server is down."""
        cfg = _make_role_setup_config(tmp_path)

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_DET_FACTORY, return_value=_mock_det_backend(available=True)),
            patch(_PATCH_ROLE_BACKEND_FACTORY, return_value=_mock_fix_backend(available=True)),
            patch("httpx.get", side_effect=OSError("connection refused")),
        ):
            result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0
        assert "Local llama-server role `qwen36_local`: not reachable" in result.output
        assert "Start the local llama-server before running check/fix" in result.output
        assert "llama-server \\" in result.output
        assert "--host 127.0.0.1 --port 8952" in result.output
        assert "Then run `certfix doctor` again" in result.output


class TestPublicConfigFiles:
    """Tests for public config files referenced from README."""

    def test_public_configs_load(self) -> None:
        """README-facing configs should stay parseable."""
        public_configs = [
            "configs/qwen36-mtp-local.yaml",
            "configs/qwen36-mtp-check.yaml",
            "configs/deepseek-v4-flash-openrouter.yaml",
            "configs/deepseek-v4-flash-api.yaml",
            "configs/gemini-3-flash-preview-openrouter.yaml",
            "configs/examples/local-detection-deepseek-fix.yaml",
            "configs/examples/deepseek-gemini-step-overrides.yaml",
        ]

        for config_path in public_configs:
            cfg = Config.load(Path(config_path))
            assert cfg.detection.backend

    def test_config_command_lists_bundled_profiles(self) -> None:
        """`certfix config --list` should show bundled public profiles."""
        runner = CliRunner()
        result = runner.invoke(main, ["config", "--list"])

        assert result.exit_code == 0
        assert "qwen36-mtp-local" in result.output
        assert "deepseek-v4-flash-api" in result.output

    def test_config_command_writes_bundled_profile(self, tmp_path: Path) -> None:
        """Bundled public profiles should be writable and parseable."""
        output = tmp_path / ".certfix.yaml"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["config", "qwen36-mtp-local", "--output", str(output)],
        )

        assert result.exit_code == 0
        assert output.exists()
        cfg = Config.load(output)
        assert cfg.detection.backend == "local_llama_server"
        assert "qwen36_local" in cfg.models

    def test_config_command_refuses_overwrite_without_force(self, tmp_path: Path) -> None:
        """Existing output files should not be overwritten unless --force is set."""
        output = tmp_path / ".certfix.yaml"
        output.write_text("sentinel", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["config", "qwen36-mtp-local", "--output", str(output)],
        )

        assert result.exit_code == 1
        assert output.read_text(encoding="utf-8") == "sentinel"


class TestFixCommand:
    """Tests for the fix command."""

    def test_fix_simple_mode_uses_direct_repair_role(self, tmp_path: Path) -> None:
        """simple mode should run the configured direct repair role."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text('char *p = malloc(10);\nfree(p);\nprintf("%s", p);\n')
        cfg = _make_role_setup_config(tmp_path)
        backend = _mock_fix_backend()
        backend.generate.return_value = """DECISION: APPLY_FIX
RULE: MEM30-C
LINE: 3
EVIDENCE: p is used after free
```c
char *p = malloc(10);
printf("%s", p);
free(p);
```
"""

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_ROLE_BACKEND_FACTORY, return_value=backend),
            patch("certfix.core.validation.run_compile_check") as mock_compile,
            patch("certfix.core.validation.run_semantic_auto_apply_check") as mock_semantic,
        ):
            mock_compile.return_value = CompileCheckResult(True, ["gcc"], 0)
            mock_semantic.return_value = SemanticAutoApplyResult(
                parse_ok=True,
                auto_apply_ok=True,
                behavior_preserved=True,
                material_behavior_delta=False,
                uncertain_material_behavior=False,
                fail_type="none",
                confidence="high",
            )

            result = runner.invoke(
                main,
                ["fix", "--format", "json", str(c_file)],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["fixes"][0]["rule_id"] == "MEM30-C"
        assert data["fixes"][0]["status"] == FinalFixStatus.FIXED.value
        assert data["fixes"][0]["timings"]["simple_repair_seconds"] >= 0
        output_dir = tmp_path / "certfix-output"
        assert (output_dir / "reports" / "fixes.json").exists()
        assert (output_dir / "reports" / "fixes.sarif").exists()
        assert (output_dir / "reports" / "summary.json").exists()
        assert (output_dir / "fixes" / "vuln.fixed.c").exists()
        assert (output_dir / "patches" / "vuln.c.patch").exists()
        assert c_file.read_text(encoding="utf-8") == (
            'char *p = malloc(10);\nfree(p);\nprintf("%s", p);\n'
        )
        mock_compile.assert_called_once()
        mock_semantic.assert_called_once()

    def test_fix_simple_mode_no_violations(self, tmp_path: Path) -> None:
        """simple mode should exit cleanly when the direct model finds nothing."""
        c_file = tmp_path / "clean.c"
        c_file.write_text("int main(void) { return 0; }\n")
        cfg = _make_role_setup_config(tmp_path)
        backend = _mock_fix_backend()
        backend.generate.return_value = "DECISION: NO_VIOLATIONS"

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_ROLE_BACKEND_FACTORY, return_value=backend),
        ):
            result = runner.invoke(main, ["fix", str(c_file)])

        assert result.exit_code == 0
        assert "No fix candidates generated" in result.output

    def test_fix_simple_code_only_profile_detects_rule_when_not_provided(
        self,
        tmp_path: Path,
    ) -> None:
        """code-only simple repair should pre-detect a rule when --rule is omitted."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text('char *p = malloc(10);\nfree(p);\nprintf("%s", p);\n')
        cfg = _make_role_setup_config(tmp_path)
        cfg.detection.backend = "api"
        cfg.detection.prompt_profile = "qwen36_certfix_check_v1"
        cfg.fix.simple_repair_profile = "qwen36_27b_complete_repair_rule_guided_v1"
        cfg.validation.compile.enabled = False
        cfg.validation.violation_removal.enabled = False
        cfg.validation.semantic.enabled = False

        repair_backend = _mock_fix_backend()
        repair_backend.generate.return_value = 'char *p = malloc(10);\nprintf("%s", p);\nfree(p);\n'
        detection_backend = _mock_det_backend()
        detection_backend.detect_qwen36_batch.return_value = {
            "0": [
                Violation(
                    rule_id="MEM30-C",
                    file_path=str(c_file),
                    line=3,
                    column=1,
                    message="use after free",
                    severity=Severity.ERROR,
                )
            ]
        }

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_ROLE_BACKEND_FACTORY, return_value=repair_backend),
            patch(_PATCH_DET_FACTORY, return_value=detection_backend),
        ):
            result = runner.invoke(
                main,
                ["fix", "--format", "json", str(c_file)],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["fixes"][0]["rule_id"] == "MEM30-C"
        assert data["fixes"][0]["success"] is True
        prompt = repair_backend.generate.call_args.args[0]
        assert "CERT-C rule MEM30-C" in prompt
        assert data["fixes"][0]["timings"]["simple_detection_seconds"] >= 0

    def test_fix_qwen36_local_detection_failure_exits_2(self, tmp_path: Path) -> None:
        """Local Qwen3.6 detection failure before repair must not look like no findings."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text('char *p = malloc(10);\nfree(p);\nprintf("%s", p);\n')
        cfg = _make_role_setup_config(tmp_path)
        cfg.detection.backend = "local_llama_server"
        cfg.detection.prompt_profile = "qwen36_certfix_check_v1"
        cfg.fix.simple_repair_profile = "qwen36_27b_complete_repair_rule_guided_v1"
        cfg.validation.compile.enabled = False
        cfg.validation.violation_removal.enabled = False
        cfg.validation.semantic.enabled = False

        repair_backend = _mock_fix_backend()
        detection_backend = _mock_det_backend()
        detection_backend.detect_qwen36_batch.side_effect = RuntimeError("server unreachable")

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_ROLE_BACKEND_FACTORY, return_value=repair_backend),
            patch(_PATCH_DET_FACTORY, return_value=detection_backend),
        ):
            result = runner.invoke(main, ["fix", str(c_file)])

        assert result.exit_code == 2
        assert "server unreachable" in result.output
        assert "No violations found" not in result.output
        repair_backend.generate.assert_not_called()

    def test_fix_simple_mode_validate_guided_retry_rescues_failure(
        self,
        tmp_path: Path,
    ) -> None:
        """simple mode should retry once when validation rejects the primary fix."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text('char *p = malloc(10);\nfree(p);\nprintf("%s", p);\n')
        cfg = _make_role_setup_config(tmp_path)
        cfg.fix.validate_guided_retry = True
        cfg.fix.retry_rule_addenda_rule_ids = ["MEM30-C"]

        backend = _mock_fix_backend()
        backend.generate.side_effect = [
            """DECISION: APPLY_FIX
RULE: MEM30-C
LINE: 3
EVIDENCE: p is used after free
```c
char *p = malloc(10)
printf("%s", p);
free(p);
```
""",
            """char *p = malloc(10);
printf("%s", p);
free(p);
""",
        ]

        runner = CliRunner()
        with (
            patch(_PATCH_CONFIG_LOAD, return_value=cfg),
            patch(_PATCH_ROLE_BACKEND_FACTORY, return_value=backend),
            patch("certfix.core.validation.run_compile_check") as mock_compile,
            patch("certfix.core.validation.run_semantic_auto_apply_check") as mock_semantic,
        ):
            mock_compile.side_effect = [
                CompileCheckResult(False, ["gcc"], 1, stderr="expected ';'"),
                CompileCheckResult(True, ["gcc"], 0),
            ]
            mock_semantic.return_value = SemanticAutoApplyResult(
                parse_ok=True,
                auto_apply_ok=True,
                behavior_preserved=True,
                material_behavior_delta=False,
                uncertain_material_behavior=False,
                fail_type="none",
                confidence="high",
            )

            result = runner.invoke(
                main,
                ["fix", "--format", "json", str(c_file)],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        fix = data["fixes"][0]
        assert fix["success"] is True
        assert fix["source"] == "retry"
        assert fix["retry_count"] == 1
        assert fix["retry"]["failure_category"] == "compile_error"
        assert "expected ';'" in fix["retry"]["failure_detail"]
        assert backend.generate.call_count == 2

    def test_fix_rejects_removed_interactive_option(self, tmp_path: Path) -> None:
        """--interactive is not part of the v0.1.0 public fix path."""
        c_file = tmp_path / "vuln.c"
        c_file.write_text('char *p = malloc(10);\nfree(p);\nprintf("%s", p);\n')

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["fix", "--interactive", "--format", "json", str(c_file)],
        )

        assert result.exit_code == 2
        assert "No such option" in result.output
        assert "--interactive" in result.output


def _make_setup_config(tmp_path: Path) -> Config:
    """Create a Config without direct local model files."""
    return Config()


def _make_role_setup_config(tmp_path: Path) -> Config:
    """Create a Config with v2 role-based model settings."""
    return Config(
        models={
            "qwen36_local": RoleModelConfig(
                backend="local_llama_server",
                profile="qwen36_27b_release",
                api=ApiConfig(
                    base_url="http://127.0.0.1:8952/v1",
                    model="qwen-local",
                    api_key_env="",
                ),
            ),
        },
    )


class TestSetupCommand:
    """Tests for the setup command."""

    def test_setup_help(self) -> None:
        """--help should show options and exit 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["setup", "--help"])

        assert result.exit_code == 0
        assert "--config" in result.output
        assert "--verbose" in result.output

    def test_setup_no_local_files(self, tmp_path: Path) -> None:
        """Setup should succeed when no direct local files are managed."""
        cfg = _make_setup_config(tmp_path)

        runner = CliRunner()
        with patch(_PATCH_CONFIG_LOAD, return_value=cfg):
            result = runner.invoke(main, ["setup"])

        assert result.exit_code == 0
        assert "No local model files are managed" in result.output

    def test_setup_role_config_reports_no_local_files(self, tmp_path: Path) -> None:
        """Server/API role configs should not require local file placement."""
        cfg = _make_role_setup_config(tmp_path)

        runner = CliRunner()
        with patch(_PATCH_CONFIG_LOAD, return_value=cfg):
            result = runner.invoke(main, ["setup"])

        assert result.exit_code == 0
        assert "Model roles:" in result.output
        assert "qwen36_local" in result.output

    def test_setup_all_files_present(self, tmp_path: Path) -> None:
        """Setup without managed local files should exit 0 with ready message."""
        cfg = _make_setup_config(tmp_path)

        runner = CliRunner()
        with patch(_PATCH_CONFIG_LOAD, return_value=cfg):
            result = runner.invoke(main, ["setup"])

        assert result.exit_code == 0
        assert "Ready to use" in result.output

    def test_setup_role_config_all_files_present(self, tmp_path: Path) -> None:
        """All role-based model files present should exit 0."""
        cfg = _make_role_setup_config(tmp_path)

        runner = CliRunner()
        with patch(_PATCH_CONFIG_LOAD, return_value=cfg):
            result = runner.invoke(main, ["setup"])

        assert result.exit_code == 0
        assert "Ready to use" in result.output
        assert "qwen36_local" in result.output

    def test_setup_external_server_config_does_not_require_gguf(self, tmp_path: Path) -> None:
        """External server configs should not ask users to place GGUF files."""
        cfg = _make_setup_config(tmp_path)

        runner = CliRunner()
        with patch(_PATCH_CONFIG_LOAD, return_value=cfg):
            result = runner.invoke(main, ["setup"])

        assert result.exit_code == 0
        assert "Missing" not in result.output
        assert "For local inference, start the configured OpenAI-compatible server" in result.output

    def test_setup_verbose_keeps_server_only_message(self, tmp_path: Path) -> None:
        """--verbose should not invent local file checks for server configs."""
        cfg = _make_setup_config(tmp_path)

        runner = CliRunner()
        with patch(_PATCH_CONFIG_LOAD, return_value=cfg):
            result = runner.invoke(main, ["setup", "--verbose"])

        assert result.exit_code == 0
        assert "No local model files are managed" in result.output

    def test_setup_custom_config(self, tmp_path: Path) -> None:
        """--config should be passed to Config.load."""
        cfg = _make_setup_config(tmp_path)
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("")

        runner = CliRunner()
        with patch(_PATCH_CONFIG_LOAD, return_value=cfg) as mock_load:
            result = runner.invoke(main, ["setup", "--config", str(config_file)])

        mock_load.assert_called_once_with(Path(str(config_file)))
        assert result.exit_code in (0, 1)
