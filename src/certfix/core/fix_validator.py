"""SPEC-compatible post-generation validator for fix candidates."""

from __future__ import annotations

from certfix.config import CompileValidationConfig
from certfix.core import validation
from certfix.core.programmatic_checks import run_programmatic_checks
from certfix.inference.base import InferenceBackend
from certfix.models import (
    CompileCheckResult,
    FinalFixStatus,
    FixResult,
    FixValidationCategory,
    FixValidatorResult,
    SemanticAutoApplyResult,
    SemanticCheckResult,
    SemanticVerdict,
    ViolationRemovalResult,
)

RETRYABLE_CATEGORIES = {
    FixValidationCategory.FORMAT_ERROR,
    FixValidationCategory.COMPILE_ERROR,
    FixValidationCategory.VIOLATION_REMAINS,
    FixValidationCategory.PROGRAMMATIC_CHECK_FAILED,
    FixValidationCategory.SEMANTIC_CHANGED,
    FixValidationCategory.REGRESSION_INTRODUCED,
    FixValidationCategory.OVER_DELETION,
}


def validate_fix_result(
    fix_result: FixResult,
    *,
    compile_config: CompileValidationConfig,
    semantic_backend: InferenceBackend | None,
    semantic_max_tokens: int,
    violation_backend: InferenceBackend | None = None,
    violation_audit_backend: InferenceBackend | None = None,
    compile_enabled: bool = True,
    violation_removal_enabled: bool = True,
    semantic_enabled: bool = True,
    programmatic_preset: str = "release_v1",
    violation_removal_method: str = "non_target_advisory",
    violation_removal_max_tokens: int = 512,
    violation_removal_override_denylist: list[str] | None = None,
) -> None:
    """Run release validation gates and update a FixResult in place."""
    format_ok = _format_ok(fix_result.fixed_code)

    if compile_enabled and format_ok:
        compile_result = validation.run_compile_check(fix_result.fixed_code, compile_config)
    else:
        compile_result = CompileCheckResult(
            ok=format_ok,
            command=[],
            returncode=0 if format_ok else 1,
        )

    removal_result: ViolationRemovalResult | None = None
    violation_removed = True
    if violation_removal_enabled:
        if violation_backend is None:
            violation_removed = False
        elif compile_result.ok and format_ok:
            removal_result = validation.run_violation_removal_check(
                fix_result.fixed_code,
                fix_result.violation.rule_id,
                violation_backend,
                method=violation_removal_method,
                max_tokens=violation_removal_max_tokens,
                original_code=fix_result.original_code,
                audit_backend=violation_audit_backend or semantic_backend,
                override_denylist=set(violation_removal_override_denylist)
                if violation_removal_override_denylist is not None
                else None,
            )
            violation_removed = removal_result.removed
        else:
            violation_removed = False

    if semantic_enabled and semantic_backend is not None and compile_result.ok and format_ok:
        semantic_auto = validation.run_semantic_auto_apply_check(
            original_code=fix_result.original_code,
            fixed_code=fix_result.fixed_code,
            target_rule_id=fix_result.violation.rule_id,
            backend=semantic_backend,
            max_tokens=semantic_max_tokens,
        )
    elif semantic_enabled:
        semantic_auto = SemanticAutoApplyResult(
            parse_ok=False,
            auto_apply_ok=False,
            behavior_preserved=None,
            material_behavior_delta=None,
            uncertain_material_behavior=True,
            fail_type="semantic_backend_unavailable",
            confidence="low",
            reason="semantic validation backend is not configured or prior gates failed",
        )
    else:
        semantic_auto = SemanticAutoApplyResult(
            parse_ok=True,
            auto_apply_ok=True,
            behavior_preserved=True,
            material_behavior_delta=False,
            uncertain_material_behavior=False,
            fail_type="none",
            confidence="high",
            reason="semantic validation disabled",
        )

    programmatic_findings = (
        run_programmatic_checks(
            original_code=fix_result.original_code,
            fixed_code=fix_result.fixed_code,
            rule_id=fix_result.violation.rule_id,
            preset=programmatic_preset,
        )
        if format_ok and compile_result.ok
        else []
    )

    validator = build_validator_result(
        format_ok=format_ok,
        compile_result=compile_result,
        removal_result=removal_result,
        violation_removed=violation_removed,
        semantic_result=semantic_auto,
        programmatic_findings=programmatic_findings,
    )

    fix_result.compile_result = compile_result
    fix_result.violation_removal_result = removal_result
    fix_result.semantic_result = _semantic_auto_to_semantic_result(semantic_auto)
    fix_result.validator_result = validator
    fix_result.final_status = _validator_to_final_status(validator)

    if not validator.auto_apply_ok:
        fix_result.success = False
        fix_result.error_message = validator.category.value


def build_validator_result(
    *,
    format_ok: bool,
    compile_result: CompileCheckResult,
    removal_result: ViolationRemovalResult | None,
    violation_removed: bool,
    semantic_result: SemanticAutoApplyResult,
    programmatic_findings: list,
) -> FixValidatorResult:
    """Build a SPEC validator object using category priority order."""
    compile_ok = compile_result.ok
    semantic_ok = semantic_result.semantic_ok
    non_target_introduced = _removal_non_target_introduced(removal_result)
    regression_free = semantic_result.fail_type != "new_regression" and not non_target_introduced
    category = _select_category(
        format_ok=format_ok,
        compile_result=compile_result,
        violation_removed=violation_removed,
        removal_result=removal_result,
        semantic_result=semantic_result,
        programmatic_findings=programmatic_findings,
        regression_free=regression_free,
    )
    auto_apply_ok = (
        format_ok
        and compile_ok
        and violation_removed
        and semantic_ok
        and regression_free
        and not programmatic_findings
        and category == FixValidationCategory.PASS
    )
    return FixValidatorResult(
        auto_apply_ok=auto_apply_ok,
        category=category,
        retryable=category in RETRYABLE_CATEGORIES,
        details=_validator_details(
            category=category,
            compile_result=compile_result,
            removal_result=removal_result,
            semantic_result=semantic_result,
            programmatic_findings=programmatic_findings,
        ),
        format_ok=format_ok,
        compile_ok=compile_ok,
        violation_removed=violation_removed,
        semantic_ok=semantic_ok,
        regression_free=regression_free,
        programmatic_findings=programmatic_findings,
        compiler_stderr=compile_result.stderr,
        semantic_check_result=semantic_result,
    )


def _format_ok(fixed_code: str) -> bool:
    stripped = fixed_code.strip()
    if not stripped:
        return False
    return "complete fixed C source file" not in stripped and not stripped.startswith("<")


def _select_category(
    *,
    format_ok: bool,
    compile_result: CompileCheckResult,
    violation_removed: bool,
    removal_result: ViolationRemovalResult | None,
    semantic_result: SemanticAutoApplyResult,
    programmatic_findings: list,
    regression_free: bool,
) -> FixValidationCategory:
    if not format_ok:
        return FixValidationCategory.FORMAT_ERROR
    if compile_result.unsupported_language:
        return FixValidationCategory.UNSUPPORTED_LANGUAGE
    if compile_result.env_missing:
        return FixValidationCategory.COMPILE_ENV_MISSING
    if not compile_result.ok:
        return FixValidationCategory.COMPILE_ERROR
    if _removal_non_target_introduced(removal_result):
        return FixValidationCategory.REGRESSION_INTRODUCED
    if _removal_non_target_manual_boundary(removal_result):
        return FixValidationCategory.MANUAL_BOUNDARY
    if not violation_removed or semantic_result.fail_type == "target_violation_remaining":
        return FixValidationCategory.VIOLATION_REMAINS
    if programmatic_findings:
        return FixValidationCategory.PROGRAMMATIC_CHECK_FAILED
    if not semantic_result.semantic_ok:
        if semantic_result.fail_type == "new_regression":
            return FixValidationCategory.REGRESSION_INTRODUCED
        if semantic_result.fail_type == "over_deletion":
            return FixValidationCategory.OVER_DELETION
        if semantic_result.fail_type == "manual_boundary" or semantic_result.confidence == "low":
            return FixValidationCategory.MANUAL_BOUNDARY
        return FixValidationCategory.SEMANTIC_CHANGED
    if not regression_free:
        return FixValidationCategory.REGRESSION_INTRODUCED
    return FixValidationCategory.PASS


def _validator_details(
    *,
    category: FixValidationCategory,
    compile_result: CompileCheckResult,
    removal_result: ViolationRemovalResult | None,
    semantic_result: SemanticAutoApplyResult,
    programmatic_findings: list,
) -> str:
    if category == FixValidationCategory.PASS:
        return "all validation gates passed"
    if category == FixValidationCategory.UNSUPPORTED_LANGUAGE:
        return compile_result.unsupported_language_reason or "unsupported source language"
    if category == FixValidationCategory.COMPILE_ENV_MISSING:
        if compile_result.missing_headers:
            headers = ", ".join(compile_result.missing_headers)
            return f"compile environment missing headers: {headers}"
        return compile_result.stderr or compile_result.stdout or "compile environment missing"
    if category == FixValidationCategory.COMPILE_ERROR:
        return compile_result.stderr or compile_result.stdout or "compile check failed"
    if category == FixValidationCategory.VIOLATION_REMAINS:
        if removal_result is not None:
            return f"{len(removal_result.remaining_violations)} target violations remain"
        return semantic_result.reason or "target violation remains"
    if (
        category == FixValidationCategory.REGRESSION_INTRODUCED
        and _removal_non_target_introduced(removal_result)
        and removal_result is not None
    ):
        return removal_result.reason
    if (
        category == FixValidationCategory.MANUAL_BOUNDARY
        and _removal_non_target_manual_boundary(removal_result)
        and removal_result is not None
    ):
        return removal_result.reason
    if category == FixValidationCategory.PROGRAMMATIC_CHECK_FAILED:
        ids = ", ".join(finding.check_id for finding in programmatic_findings)
        return f"programmatic checks blocked auto-apply: {ids}"
    return semantic_result.reason or category.value


def _removal_non_target_introduced(
    removal_result: ViolationRemovalResult | None,
) -> bool:
    return (
        removal_result is not None
        and removal_result.method in {"non_target_advisory", "release_v3"}
        and removal_result.non_target_introduced is True
    )


def _removal_non_target_manual_boundary(
    removal_result: ViolationRemovalResult | None,
) -> bool:
    return (
        removal_result is not None
        and removal_result.method in {"non_target_advisory", "release_v3"}
        and removal_result.non_target_audit_blocking is True
        and removal_result.non_target_introduced is not True
    )


def _semantic_auto_to_semantic_result(result: SemanticAutoApplyResult) -> SemanticCheckResult:
    verdict = SemanticVerdict.PASS if result.semantic_ok else SemanticVerdict.FAIL
    if not result.parse_ok or result.uncertain_material_behavior or result.confidence == "low":
        verdict = SemanticVerdict.UNCERTAIN
    return SemanticCheckResult(
        verdict=verdict,
        semantic_preserved=result.behavior_preserved,
        target_violation_removed=result.fail_type != "target_violation_remaining",
        new_regression=result.fail_type == "new_regression",
        reason=result.reason,
        raw_output=result.raw_output,
    )


def _validator_to_final_status(validator: FixValidatorResult) -> FinalFixStatus:
    if validator.category == FixValidationCategory.PASS:
        return FinalFixStatus.FIXED
    if validator.category == FixValidationCategory.UNSUPPORTED_LANGUAGE:
        return FinalFixStatus.UNSUPPORTED_LANGUAGE
    if validator.category == FixValidationCategory.COMPILE_ENV_MISSING:
        return FinalFixStatus.COMPILE_ENV_MISSING
    if validator.category == FixValidationCategory.COMPILE_ERROR:
        return FinalFixStatus.COMPILE_FAILED
    if validator.category == FixValidationCategory.VIOLATION_REMAINS:
        return FinalFixStatus.VIOLATION_REMAINING
    if validator.category == FixValidationCategory.REGRESSION_INTRODUCED:
        return FinalFixStatus.REGRESSION_RISK
    if validator.category == FixValidationCategory.FORMAT_ERROR:
        return FinalFixStatus.MODEL_ERROR
    return FinalFixStatus.SEMANTIC_RISK
