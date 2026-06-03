"""Validate-guided retry prompt construction for Qwen3.6 repair."""
# ruff: noqa: E501

from __future__ import annotations

import re
from dataclasses import dataclass

from certfix.core.simple_repair import strip_c_comments
from certfix.inference.base import InferenceBackend
from certfix.inference.parsing import extract_fixed_code
from certfix.models import FinalFixStatus, FixResult, SemanticVerdict

RETRYABLE_FAILURE_CATEGORIES = {
    "format_error",
    "compile_error",
    "violation_remains",
    "programmatic_check_failed",
    "semantic_changed",
    "regression_introduced",
    "over_deletion",
}

FAILURE_CATEGORY_ADDENDA = {
    "format_error": "Produce exactly one complete C translation unit or snippet matching the original scope. No prose.",
    "compile_error": "Fix the compile error first. Keep the previous repair intent and change only declarations, includes, casts, or expressions needed to compile.",
    "violation_remains": "Find the remaining target-rule operation in the previous fixed code and repair that location. Do not rewrite unrelated code.",
    "programmatic_check_failed": "Repair the structural semantic-risk pattern reported by the programmatic checker. Keep the target-rule repair, but remove the exact risky transformation described in the findings.",
    "semantic_changed": "Restore the original valid-input behavior and data/control flow while keeping the rule violation removed.",
    "regression_introduced": "Remove the newly introduced defect while preserving both the original behavior and the target-rule repair.",
    "over_deletion": "Restore the deleted behavior from the original code, then apply a local rule-compliant fix instead of bypassing the code path.",
}

RULE_RETRY_ADDENDA_V1 = {
    "ARR37-C": """For ARR37-C, repair the actual remaining non-array pointer arithmetic, not only the first indexed access.
- Do not cast a scalar or struct object to char*, unsigned char*, or uint8_t* and then add an offset.
- Do not return a pointer into a local union, local byte buffer, temporary copy, or unrelated static copy when the original API expects a pointer into live program state.
- If the offset selects a known member, replace offset arithmetic with explicit member selection, a switch over valid offsets, or a table of member addresses that point into the live object.
- If byte-addressable random access is truly required, the bytes must be stored in an actual array object that owns the state. Keep reads and writes connected to the original state.
- Preserve valid nonzero-offset behavior. Returning only the base object, returning NULL for all nonzero offsets, or dropping write-back behavior is a semantic failure.""",
    "CON31-C": """For CON31-C, a mutex may be destroyed only after no thread can hold it, wait on it, or lock it again.
- Do not use pthread_mutex_trylock(), pthread_mutex_timedlock(), sleep, or retry loops as proof that destroy is safe.
- Do not delete worker processing, cleanup, or state updates just to avoid the destroy call.
- Establish shutdown/retired state under the protecting lock or with an atomic flag, prevent new users from acquiring the object, then wait for existing users to leave.
- If a worker thread exists, signal shutdown, wake it if needed, join it, and only then destroy the mutex and free the owning object.
- Update registries/lists in an order that prevents both new lookup and use-after-free.
- If the object has static lifetime and explicit destroy is not required, leaving the mutex alive is acceptable only when cleanup behavior and public semantics are still preserved.""",
    "DCL37-C": """For DCL37-C, remove reserved identifiers without changing unrelated API behavior.
- Rename every identifier reserved to the implementation, including leading underscore names and names reserved by headers.
- Do not leave declarations, macros, typedefs, fields, or extern-visible globals with the reserved spelling.
- If a public reserved identifier must be renamed, update all uses consistently and preserve storage duration, linkage, type, and initialization.
- Do not delete functionality or hide symbols solely to avoid a reserved name.
- Avoid introducing new reserved identifiers while renaming.""",
    "POS48-C": """For POS48-C, preserve the original synchronization protocol while ensuring that each mutex is unlocked or destroyed only by a valid owner at a valid lifetime point.
- Do not simply delete unlock, destroy, wakeup, cleanup, or worker logic; that usually breaks semantics.
- If a function unlocks without owning the mutex, add the missing matching lock in that same control path or move the unlock back to the owning thread.
- If another thread needs to request release, change it to a cooperative request flag or condition notification; the owner must perform the unlock.
- Do not free mutex storage until all users are stopped or have released their references.
- Protect shared ownership/state flags with a mutex or atomics. Do not read or write them as plain shared variables.
- Avoid trylock as a safety proof. It does not establish that no other thread will use the mutex after the check.""",
    "SIG30-C": """For SIG30-C, the signal handler itself must do only async-signal-safe work, but the original reporting or state behavior should be moved rather than deleted.
- In the handler, only set volatile sig_atomic_t flags, store minimal signal-safe state, call async-signal-safe functions such as write() with fixed data, or call _Exit/_exit when termination is required.
- Do not call formatting, allocation, stdio, time conversion, logging wrappers, locale functions, or non-atomic shared-state updates inside the handler.
- Preserve external symbols, error indicators, and observable reporting behavior by performing detailed formatting/logging later in normal control flow.
- If the original handler recorded which signal occurred, keep that information with sig_atomic_t-compatible storage.
- Do not make the handler exit before deferred reporting code has any chance to run unless the original semantics required immediate termination.""",
    "ENV33-C": """For ENV33-C, replacing system() must preserve the command's data flow and argument semantics without relying on a shell.
- Build an explicit argv list with exact argument count and NULL termination. Do not drop trailing paths, modes, flags, or user-visible arguments.
- Reimplement shell features explicitly. A literal "*", "|", ">", "$VAR", or quoted command fragment is usually a semantic bug unless the original wanted that literal text.
- Preserve pipe direction: data that used to flow into a command's stdin must still flow into that child's stdin, and captured output must come from the correct stdout/stderr stream.
- Preserve formatting behavior. If replacing a composed command string, verify that printf-family argument counts and specifiers still match.
- Do not replace system() with another unsafe shell invocation. Prefer fork/exec, posix_spawn, or direct library calls when the code scope supports them.
- Do not introduce unrelated unsafe library calls while repairing system().""",
}


@dataclass(frozen=True)
class RetryFailure:
    """Validation failure category and detail used to route retry."""

    category: str
    detail: str
    retryable: bool


def classify_retry_failure(fix_result: FixResult) -> RetryFailure:
    """Map validation output to the retry prompt failure category."""
    if fix_result.validator_result is not None:
        category = fix_result.validator_result.category.value
        return RetryFailure(
            category,
            fix_result.validator_result.details,
            fix_result.validator_result.retryable,
        )

    if fix_result.compile_result is not None and not fix_result.compile_result.ok:
        detail = fix_result.compile_result.stderr or fix_result.compile_result.stdout
        if not detail and fix_result.compile_result.timed_out:
            detail = "compile check timed out"
        return RetryFailure("compile_error", detail or "compile check failed", True)

    semantic = fix_result.semantic_result
    if semantic is not None:
        if semantic.target_violation_removed is False:
            return RetryFailure("violation_remains", semantic.reason or "target violation remains", True)
        if semantic.new_regression is True:
            return RetryFailure(
                "regression_introduced",
                semantic.reason or "semantic validator reported a new regression",
                True,
            )
        if semantic.semantic_preserved is False:
            return RetryFailure(
                "semantic_changed",
                semantic.reason or "semantic validator reported changed behavior",
                True,
            )
        if semantic.verdict != SemanticVerdict.PASS:
            return RetryFailure(
                "semantic_changed",
                semantic.reason or "semantic validator was uncertain",
                True,
            )

    status = fix_result.final_status
    if status == FinalFixStatus.VIOLATION_REMAINING:
        return RetryFailure("violation_remains", fix_result.error_message or status.value, True)
    if status == FinalFixStatus.REGRESSION_RISK:
        return RetryFailure("regression_introduced", fix_result.error_message or status.value, True)
    if status == FinalFixStatus.COMPILE_FAILED:
        return RetryFailure("compile_error", fix_result.error_message or status.value, True)
    if status == FinalFixStatus.MODEL_ERROR:
        return RetryFailure("format_error", fix_result.error_message or status.value, True)

    return RetryFailure("manual_boundary", fix_result.error_message or "not retryable", False)


def build_validate_guided_retry_prompt(
    *,
    original_code: str,
    previous_fixed_code: str,
    rule_id: str,
    rule_title: str,
    failure_category: str,
    failure_detail: str,
    compiler_stderr: str = "",
    programmatic_findings: list[dict[str, object]] | None = None,
    semantic_summary: dict[str, object] | None = None,
    use_rule_addenda_v1: bool = True,
    enabled_rule_addenda: list[str] | None = None,
) -> tuple[str, str | None]:
    """Build the release-side validator-guided retry prompt."""
    specific = FAILURE_CATEGORY_ADDENDA.get(
        failure_category,
        "Repair the validator failure with the smallest possible edit.",
    )
    enabled = set(enabled_rule_addenda or [])
    rule_addendum = (
        RULE_RETRY_ADDENDA_V1.get(rule_id, "")
        if use_rule_addenda_v1 and (not enabled or rule_id in enabled)
        else ""
    )
    rule_addendum_id = "qwen36_retry_rule_addenda_v1" if rule_addendum else None
    rule_addendum_block = (
        f"\nRule-specific retry guidance for CERT-C {rule_id}:\n{rule_addendum}\n"
        if rule_addendum
        else ""
    )
    extra_blocks: list[str] = []
    if compiler_stderr:
        extra_blocks.append(f"Compiler stderr:\n```text\n{compiler_stderr}\n```")
    if programmatic_findings:
        extra_blocks.append(f"Programmatic findings:\n{programmatic_findings}")
    if semantic_summary:
        extra_blocks.append(f"Semantic summary:\n{semantic_summary}")
    extra_context = "\n\n".join(extra_blocks)
    extra_context_block = f"\n\nAdditional validator context:\n{extra_context}\n" if extra_context else ""

    prompt = f"""You previously generated a fix for CERT-C {rule_id}: {rule_title}, but it failed validation.

Original code:
```c
{original_code}
```

Previous fixed code:
```c
{previous_fixed_code}
```

Validation failure:
- category: {failure_category}
- detail: {failure_detail}
{extra_context_block}

Repair task:
- {specific}
{rule_addendum_block}
- Repair the previous fixed code with the smallest possible edit.
- Prefer preserving the structure and successful parts of the previous fixed code.
- Do not revert to the original vulnerable code.
- Remove the target {rule_id} violation completely.
- Preserve valid-input semantics, state updates, side effects, cleanup paths, error paths, and public contracts except where the rule requires a narrow change.
- Do not introduce new C11 compile errors or new safety defects.
- Output only the complete corrected C code. No explanation and no markdown.
"""
    return prompt, rule_addendum_id


def run_validate_guided_retry(
    *,
    primary: FixResult,
    backend: InferenceBackend,
    max_tokens: int,
    use_rule_addenda_v1: bool = True,
    enabled_rule_addenda: list[str] | None = None,
) -> FixResult | None:
    """Generate a single retry candidate for a failed primary fix."""
    failure = classify_retry_failure(primary)
    if not failure.retryable or failure.category not in RETRYABLE_FAILURE_CATEGORIES:
        return None

    prompt, rule_addendum_id = build_validate_guided_retry_prompt(
        original_code=primary.original_code,
        previous_fixed_code=primary.fixed_code,
        rule_id=primary.violation.rule_id,
        rule_title=primary.violation.message,
        failure_category=failure.category,
        failure_detail=failure.detail,
        compiler_stderr=primary.validator_result.compiler_stderr
        if primary.validator_result
        else primary.compile_result.stderr
        if primary.compile_result
        else "",
        programmatic_findings=[
            finding.to_dict() for finding in primary.validator_result.programmatic_findings
        ]
        if primary.validator_result
        else None,
        semantic_summary=primary.validator_result.semantic_check_result.to_dict()
        if primary.validator_result and primary.validator_result.semantic_check_result
        else None,
        use_rule_addenda_v1=use_rule_addenda_v1,
        enabled_rule_addenda=enabled_rule_addenda,
    )
    output = backend.generate(prompt, max_tokens=max_tokens, temperature=0.0)
    fixed_code = strip_c_comments(_extract_retry_code(output))
    if not fixed_code:
        return None

    retry = FixResult(
        violation=primary.violation,
        original_code=primary.original_code,
        fixed_code=fixed_code,
        success=True,
        source="retry",
        retry_count=primary.retry_count + 1,
        artifact_original_code=primary.artifact_original_code,
        retry_metadata={
            "runtime_label": "retry_on_budget1024",
            "reasoning": "on",
            "reasoning_budget": 1024,
            "failure_category": failure.category,
            "failure_detail": failure.detail,
            "rule_addendum_id": rule_addendum_id,
            "primary_status": primary.final_status.value if primary.final_status else None,
        },
    )
    return retry


def _extract_retry_code(output: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
    cleaned = re.sub(
        r"<\|channel\|>analysis<\|message\|>.*?(?=<\|channel\|>|<\|end\|>|$)",
        "",
        cleaned,
        flags=re.DOTALL,
    ).strip()
    return str(extract_fixed_code(cleaned))
