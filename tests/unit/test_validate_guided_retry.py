"""Tests for validate-guided retry prompt construction."""

from unittest.mock import MagicMock

from certfix.core.validate_guided_retry import (
    _extract_retry_code,
    build_validate_guided_retry_prompt,
    classify_retry_failure,
    run_validate_guided_retry,
)
from certfix.models import (
    CompileCheckResult,
    FinalFixStatus,
    FixResult,
    FixValidationCategory,
    FixValidatorResult,
    ProgrammaticFinding,
    SemanticAutoApplyResult,
    SemanticCheckResult,
    SemanticVerdict,
    Severity,
    Violation,
)


def _primary(status: FinalFixStatus = FinalFixStatus.COMPILE_FAILED) -> FixResult:
    violation = Violation(
        rule_id="ARR37-C",
        file_path="test.c",
        line=1,
        column=1,
        message="CERT-C ARR37-C: pointer arithmetic",
        severity=Severity.ERROR,
    )
    return FixResult(
        violation=violation,
        original_code="int x; char *p = (char *)&x + 1;",
        fixed_code="int x; char *p = (char *)&x + 1;",
        success=False,
        final_status=status,
        compile_result=CompileCheckResult(False, ["gcc"], 1, stderr="syntax error"),
    )


def test_classify_compile_failure_is_retryable() -> None:
    failure = classify_retry_failure(_primary())

    assert failure.category == "compile_error"
    assert failure.retryable is True
    assert "syntax error" in failure.detail


def test_classify_semantic_target_remaining() -> None:
    result = _primary(FinalFixStatus.VIOLATION_REMAINING)
    result.compile_result = CompileCheckResult(True, ["gcc"], 0)
    result.semantic_result = SemanticCheckResult(
        verdict=SemanticVerdict.PASS,
        semantic_preserved=True,
        target_violation_removed=False,
        new_regression=False,
        reason="ARR37-C remains",
    )

    failure = classify_retry_failure(result)

    assert failure.category == "violation_remains"
    assert failure.detail == "ARR37-C remains"


def test_retry_prompt_includes_selected_rule_addendum() -> None:
    prompt, addendum_id = build_validate_guided_retry_prompt(
        original_code="int x;",
        previous_fixed_code="int x;",
        rule_id="ARR37-C",
        rule_title="pointer arithmetic",
        failure_category="violation_remains",
        failure_detail="still present",
        enabled_rule_addenda=["ARR37-C"],
    )

    assert addendum_id == "qwen36_retry_rule_addenda_v1"
    assert "Rule-specific retry guidance for CERT-C ARR37-C" in prompt
    assert "Validation failure:" in prompt
    assert "Output only the complete corrected C code" in prompt


def test_retry_prompt_includes_dcl37_addendum() -> None:
    prompt, addendum_id = build_validate_guided_retry_prompt(
        original_code="int _reserved;",
        previous_fixed_code="int _reserved;",
        rule_id="DCL37-C",
        rule_title="reserved identifiers",
        failure_category="violation_remains",
        failure_detail="reserved identifier remains",
        enabled_rule_addenda=["DCL37-C"],
    )

    assert addendum_id == "qwen36_retry_rule_addenda_v1"
    assert "Rule-specific retry guidance for CERT-C DCL37-C" in prompt
    assert "Rename every identifier reserved to the implementation" in prompt


def test_retry_prompt_includes_programmatic_context() -> None:
    prompt, _addendum_id = build_validate_guided_retry_prompt(
        original_code="int i; sizeof(i++);",
        previous_fixed_code="int i; i++; sizeof(i);",
        rule_id="EXP44-C",
        rule_title="sizeof side effects",
        failure_category="programmatic_check_failed",
        failure_detail="programmatic check blocked auto-apply",
        compiler_stderr="",
        programmatic_findings=[
            {
                "check_id": "exp44_sizeof_side_effect_materialized",
                "rule_id": "EXP44-C",
                "verdict": "fail",
                "reason": "increment materialized",
                "evidence": {},
            }
        ],
        semantic_summary={"auto_apply_ok": False, "fail_type": "none"},
    )

    assert "Programmatic findings:" in prompt
    assert "exp44_sizeof_side_effect_materialized" in prompt
    assert "Semantic summary:" in prompt


def test_classify_prefers_validator_result() -> None:
    primary = _primary()
    primary.validator_result = FixValidatorResult(
        auto_apply_ok=False,
        category=FixValidationCategory.PROGRAMMATIC_CHECK_FAILED,
        retryable=True,
        details="programmatic checks blocked auto-apply",
        format_ok=True,
        compile_ok=True,
        violation_removed=True,
        semantic_ok=False,
        regression_free=True,
        programmatic_findings=[
            ProgrammaticFinding(
                "exp44_sizeof_side_effect_materialized",
                "EXP44-C",
                "fail",
                "blocked",
                {},
            )
        ],
        semantic_check_result=SemanticAutoApplyResult(
            parse_ok=True,
            auto_apply_ok=False,
            behavior_preserved=True,
            material_behavior_delta=False,
            uncertain_material_behavior=False,
            fail_type="none",
            confidence="high",
        ),
    )

    failure = classify_retry_failure(primary)

    assert failure.category == "programmatic_check_failed"
    assert failure.retryable is True


def test_run_validate_guided_retry_generates_retry_candidate() -> None:
    backend = MagicMock()
    backend.generate.return_value = "int x; /* stale comment */ char *p = NULL;"

    retry = run_validate_guided_retry(
        primary=_primary(),
        backend=backend,
        max_tokens=4096,
        enabled_rule_addenda=["ARR37-C"],
    )

    assert retry is not None
    assert retry.success is True
    assert retry.source == "retry"
    assert retry.retry_count == 1
    assert retry.fixed_code == "int x;  char *p = NULL;"
    assert "stale comment" not in retry.fixed_code
    assert retry.retry_metadata["failure_category"] == "compile_error"
    assert retry.retry_metadata["rule_addendum_id"] == "qwen36_retry_rule_addenda_v1"
    backend.generate.assert_called_once()


def test_extract_retry_code_preserves_angle_bracket_includes() -> None:
    output = "#include <stdio.h>\n#include <stdlib.h>\nint main(void) { return 0; }"

    assert _extract_retry_code(output) == output
