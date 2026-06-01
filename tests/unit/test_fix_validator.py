"""Tests for the SPEC-compatible fix validator."""

from unittest.mock import patch

from certfix.config import CompileValidationConfig
from certfix.core.fix_validator import validate_fix_result
from certfix.models import (
    CompileCheckResult,
    FinalFixStatus,
    FixResult,
    FixValidationCategory,
    ProgrammaticFinding,
    SemanticAutoApplyResult,
    Severity,
    Violation,
    ViolationRemovalResult,
)


def _fix(rule_id: str = "MEM30-C") -> FixResult:
    return FixResult(
        violation=Violation(
            rule_id=rule_id,
            file_path="test.c",
            line=1,
            column=1,
            message=f"CERT-C {rule_id}",
            severity=Severity.ERROR,
        ),
        original_code='free(p);\nprintf("%s", p);\n',
        fixed_code='printf("%s", p);\nfree(p);\n',
        success=True,
    )


def _semantic_pass() -> SemanticAutoApplyResult:
    return SemanticAutoApplyResult(
        parse_ok=True,
        auto_apply_ok=True,
        behavior_preserved=True,
        material_behavior_delta=False,
        uncertain_material_behavior=False,
        fail_type="none",
        confidence="high",
        reason="ok",
    )


def test_validator_pass_allows_auto_apply() -> None:
    fix = _fix()

    with patch("certfix.core.validation.run_compile_check") as compile_check:
        compile_check.return_value = CompileCheckResult(True, ["gcc"], 0)

        validate_fix_result(
            fix,
            compile_config=CompileValidationConfig(),
            semantic_backend=None,
            semantic_max_tokens=1024,
            violation_removal_enabled=False,
            semantic_enabled=False,
        )

    assert fix.success is True
    assert fix.final_status == FinalFixStatus.FIXED
    assert fix.validator_result is not None
    assert fix.validator_result.category == FixValidationCategory.PASS
    assert fix.validator_result.auto_apply_ok is True


def test_validator_programmatic_finding_blocks_before_semantic_category() -> None:
    fix = _fix("EXP44-C")
    fix.original_code = "void f(int i) { size_t n = sizeof(i++); }"
    fix.fixed_code = "void f(int i) { i++; size_t n = sizeof(i); }"

    with patch("certfix.core.validation.run_compile_check") as compile_check:
        compile_check.return_value = CompileCheckResult(True, ["gcc"], 0)

        validate_fix_result(
            fix,
            compile_config=CompileValidationConfig(),
            semantic_backend=None,
            semantic_max_tokens=1024,
            violation_removal_enabled=False,
            semantic_enabled=False,
        )

    assert fix.success is False
    assert fix.final_status == FinalFixStatus.SEMANTIC_RISK
    assert fix.validator_result is not None
    assert fix.validator_result.category == FixValidationCategory.PROGRAMMATIC_CHECK_FAILED
    assert fix.validator_result.programmatic_findings[0].check_id == (
        "exp44_sizeof_side_effect_materialized"
    )


def test_validator_category_priority_compile_before_programmatic() -> None:
    fix = _fix("EXP44-C")
    fix.original_code = "void f(int i) { size_t n = sizeof(i++); }"
    fix.fixed_code = "void f(int i) { i++; size_t n = sizeof(i)"

    with patch("certfix.core.validation.run_compile_check") as compile_check:
        compile_check.return_value = CompileCheckResult(False, ["gcc"], 1, stderr="syntax")

        validate_fix_result(
            fix,
            compile_config=CompileValidationConfig(),
            semantic_backend=None,
            semantic_max_tokens=1024,
            violation_removal_enabled=False,
        )

    assert fix.validator_result is not None
    assert fix.validator_result.category == FixValidationCategory.COMPILE_ERROR
    assert fix.final_status == FinalFixStatus.COMPILE_FAILED


def test_validator_maps_missing_header_to_compile_env_missing() -> None:
    """Header lookup failures should be separated from model compile errors."""
    fix = _fix("MEM30-C")

    with patch("certfix.core.validation.run_compile_check") as compile_check:
        compile_check.return_value = CompileCheckResult(
            False,
            ["gcc"],
            1,
            stderr='fatal error: std_testcase.h: No such file or directory',
            env_missing=True,
            missing_headers=["std_testcase.h"],
        )

        validate_fix_result(
            fix,
            compile_config=CompileValidationConfig(),
            semantic_backend=None,
            semantic_max_tokens=1024,
            violation_removal_enabled=False,
        )

    assert fix.validator_result is not None
    assert fix.validator_result.category == FixValidationCategory.COMPILE_ENV_MISSING
    assert fix.validator_result.retryable is False
    assert fix.final_status == FinalFixStatus.COMPILE_ENV_MISSING


def test_validator_maps_cpp_to_unsupported_language() -> None:
    """C++ samples should be excluded from C-only fix metrics."""
    fix = _fix("MEM30-C")

    with patch("certfix.core.validation.run_compile_check") as compile_check:
        compile_check.return_value = CompileCheckResult(
            False,
            ["gcc"],
            1,
            stderr="error: unknown type name 'namespace'",
            unsupported_language=True,
            unsupported_language_reason="C++ namespace syntax used in C-only mode",
        )

        validate_fix_result(
            fix,
            compile_config=CompileValidationConfig(),
            semantic_backend=None,
            semantic_max_tokens=1024,
            violation_removal_enabled=False,
        )

    assert fix.validator_result is not None
    assert fix.validator_result.category == FixValidationCategory.UNSUPPORTED_LANGUAGE
    assert fix.validator_result.retryable is False
    assert fix.final_status == FinalFixStatus.UNSUPPORTED_LANGUAGE


def test_validator_maps_non_target_introduced_to_regression_risk() -> None:
    """Release v3 non-target introduced audit should report regression risk."""
    fix = _fix("DCL30-C")

    with (
        patch("certfix.core.validation.run_compile_check") as compile_check,
        patch("certfix.core.validation.run_violation_removal_check") as removal_check,
    ):
        compile_check.return_value = CompileCheckResult(True, ["gcc"], 0)
        removal_check.return_value = ViolationRemovalResult(
            removed=False,
            target_rule_id="DCL30-C",
            remaining_violations=[],
            method="non_target_advisory",
            reason="post-fix non-target violation introduced",
            non_target_introduced=True,
            non_target_audit_blocking=True,
        )

        validate_fix_result(
            fix,
            compile_config=CompileValidationConfig(),
            semantic_backend=None,
            semantic_max_tokens=1024,
            violation_backend=object(),  # type: ignore[arg-type]
            violation_audit_backend=None,
            semantic_enabled=False,
        )

    assert fix.success is False
    assert fix.final_status == FinalFixStatus.REGRESSION_RISK
    assert fix.validator_result is not None
    assert fix.validator_result.category == FixValidationCategory.REGRESSION_INTRODUCED


def test_validator_maps_uncertain_non_target_audit_to_manual_boundary() -> None:
    """Release v3 uncertain non-target audit should fail closed as manual boundary."""
    fix = _fix("MEM30-C")

    with (
        patch("certfix.core.validation.run_compile_check") as compile_check,
        patch("certfix.core.validation.run_violation_removal_check") as removal_check,
    ):
        compile_check.return_value = CompileCheckResult(True, ["gcc"], 0)
        removal_check.return_value = ViolationRemovalResult(
            removed=False,
            target_rule_id="MEM30-C",
            remaining_violations=[],
            method="non_target_advisory",
            reason="post-fix non-target audit uncertain",
            non_target_introduced=False,
            non_target_audit_blocking=True,
        )

        validate_fix_result(
            fix,
            compile_config=CompileValidationConfig(),
            semantic_backend=None,
            semantic_max_tokens=1024,
            violation_backend=object(),  # type: ignore[arg-type]
            violation_audit_backend=None,
            semantic_enabled=False,
        )

    assert fix.success is False
    assert fix.final_status == FinalFixStatus.SEMANTIC_RISK
    assert fix.validator_result is not None
    assert fix.validator_result.category == FixValidationCategory.MANUAL_BOUNDARY


def test_programmatic_finding_dict_shape() -> None:
    finding = ProgrammaticFinding(
        check_id="x",
        rule_id="EXP44-C",
        verdict="fail",
        reason="blocked",
        evidence={"k": "v"},
    )

    assert finding.to_dict() == {
        "check_id": "x",
        "rule_id": "EXP44-C",
        "verdict": "fail",
        "reason": "blocked",
        "evidence": {"k": "v"},
    }
