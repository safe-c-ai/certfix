"""Validation gates for generated fixes."""

import json
import re
import subprocess
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any, cast

from certfix.config import CompileValidationConfig
from certfix.core.detector import Detector
from certfix.exceptions import InferenceError
from certfix.inference.base import InferenceBackend
from certfix.inference.parsing import (
    parse_non_target_introduced_audit,
    parse_original_target_rule_audit,
    parse_semantic_auto_apply_check,
    parse_semantic_check,
    parse_violation_removal_audit,
)
from certfix.models import (
    CompileCheckResult,
    FinalFixStatus,
    SemanticAutoApplyResult,
    SemanticCheckResult,
    SemanticVerdict,
    Severity,
    Violation,
    ViolationRemovalResult,
)
from certfix.prompts import (
    NON_TARGET_INTRODUCED_AUDIT_PROMPT,
    ORIGINAL_TARGET_RULE_AUDIT_PROMPT,
    SEMANTIC_AUTO_APPLY_PROMPT,
    SEMANTIC_CHECK_GRAMMAR,
    SEMANTIC_CHECK_PROMPT,
    VIOLATION_REMOVAL_AUDIT_PROMPT,
)

DEFAULT_TARGET_OVERRIDE_DENYLIST = {"SIG34-C", "STR31-C"}
_MISSING_HEADER_RE = re.compile(r"fatal error:\s+([^:\n]+):\s+No such file or directory")
_CPP_HEADERS = {"algorithm", "iostream", "list", "map", "string", "vector"}


def run_compile_check(
    code: str,
    config: CompileValidationConfig | None = None,
) -> CompileCheckResult:
    """Run the Stage 5 compile validation gate on generated C code."""
    cfg = config or CompileValidationConfig()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
        f.write(code)
        temp_path = Path(f.name)

    include_args = [arg for path in cfg.include_paths for arg in ("-I", path)]
    command = [cfg.command, *cfg.args, *include_args, str(temp_path)]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
            check=False,
        )
        missing_headers = _missing_headers(result.stderr)
        unsupported_language_reason = _unsupported_language_reason(
            result.stderr,
            missing_headers,
        )
        return CompileCheckResult(
            ok=result.returncode == 0,
            command=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            env_missing=bool(missing_headers),
            missing_headers=missing_headers,
            unsupported_language=bool(unsupported_language_reason),
            unsupported_language_reason=unsupported_language_reason,
        )
    except subprocess.TimeoutExpired as e:
        return CompileCheckResult(
            ok=False,
            command=command,
            returncode=None,
            stdout=e.stdout or "",
            stderr=e.stderr or "",
            timed_out=True,
        )
    finally:
        temp_path.unlink(missing_ok=True)


def _missing_headers(stderr: str) -> list[str]:
    return sorted(set(_MISSING_HEADER_RE.findall(stderr)))


def _unsupported_language_reason(stderr: str, missing_headers: list[str]) -> str:
    """Classify C++ code compiled through the C-only release compiler path."""
    if any(header in _CPP_HEADERS for header in missing_headers):
        return "C++ standard library header used in C-only mode"
    lowered = stderr.lower()
    if "unknown type name" in lowered and "namespace" in lowered:
        return "C++ namespace syntax used in C-only mode"
    if "'new' undeclared" in lowered or "‘new’ undeclared" in lowered:
        return "C++ new expression used in C-only mode"
    if "'delete' undeclared" in lowered or "‘delete’ undeclared" in lowered:
        return "C++ delete expression used in C-only mode"
    return ""


def run_violation_removal_check(
    code: str,
    target_rule_id: str,
    backend: InferenceBackend,
    *,
    method: str = "detector",
    max_tokens: int = 512,
    original_code: str | None = None,
    audit_backend: InferenceBackend | None = None,
    override_denylist: set[str] | None = None,
) -> ViolationRemovalResult:
    """Run the Stage 6 violation removal gate."""
    if method in {"non_target_advisory", "release_v3"}:
        effective_denylist = (
            DEFAULT_TARGET_OVERRIDE_DENYLIST if override_denylist is None else override_denylist
        )
        return _run_non_target_advisory_check(
            code=code,
            original_code=original_code,
            target_rule_id=target_rule_id,
            detector_backend=backend,
            audit_backend=audit_backend or backend,
            max_tokens=max_tokens,
            override_denylist=effective_denylist,
        )
    if method == "target_only_override":
        effective_denylist = (
            DEFAULT_TARGET_OVERRIDE_DENYLIST if override_denylist is None else override_denylist
        )
        return _run_target_only_override_check(
            code=code,
            original_code=original_code,
            target_rule_id=target_rule_id,
            detector_backend=backend,
            audit_backend=audit_backend or backend,
            max_tokens=max_tokens,
            override_denylist=effective_denylist,
        )
    if method == "target_rule_audit":
        try:
            return _run_target_rule_audit_check(
                code=code,
                target_rule_id=target_rule_id,
                backend=audit_backend or backend,
                max_tokens=max_tokens,
            )
        except InferenceError:
            pass

    remaining = _detect_code(code, backend, rules=[target_rule_id])
    return ViolationRemovalResult(
        removed=len(remaining) == 0,
        target_rule_id=target_rule_id,
        remaining_violations=remaining,
        method="detector",
        post_fix_detected_rules=sorted({violation.rule_id for violation in remaining}),
        post_fix_detected_any=bool(remaining),
        target_rule_detected=bool(remaining),
    )


def _run_target_only_override_check(
    *,
    code: str,
    original_code: str | None,
    target_rule_id: str,
    detector_backend: InferenceBackend,
    audit_backend: InferenceBackend,
    max_tokens: int,
    override_denylist: set[str],
) -> ViolationRemovalResult:
    post_fix_violations = _detect_code(code, detector_backend)
    detected_rules = sorted({violation.rule_id for violation in post_fix_violations})
    detected_rule_set = set(detected_rules)
    target_only = bool(detected_rule_set) and detected_rule_set <= {target_rule_id}

    if not post_fix_violations:
        return ViolationRemovalResult(
            removed=True,
            target_rule_id=target_rule_id,
            remaining_violations=[],
            method="target_only_override",
            reason="post-fix detector found no violations",
            post_fix_detected_rules=[],
            post_fix_detected_any=False,
            target_rule_detected=False,
        )

    if not target_only:
        return ViolationRemovalResult(
            removed=False,
            target_rule_id=target_rule_id,
            remaining_violations=post_fix_violations,
            method="target_only_override",
            reason="post-fix detector found non-target violations",
            post_fix_detected_rules=detected_rules,
            post_fix_detected_any=True,
            target_rule_detected=target_rule_id in detected_rule_set,
        )

    if target_rule_id in override_denylist:
        return _target_override_denied_result(
            method="target_only_override",
            target_rule_id=target_rule_id,
            post_fix_violations=post_fix_violations,
            detected_rules=detected_rules,
            reason=f"target-only override denied for {target_rule_id}",
        )

    if original_code is None:
        return _target_override_denied_result(
            method="target_only_override",
            target_rule_id=target_rule_id,
            post_fix_violations=post_fix_violations,
            detected_rules=detected_rules,
            reason="original target audit is required for target-only override",
        )

    return _run_target_override_audit(
        code=code,
        original_code=original_code,
        target_rule_id=target_rule_id,
        audit_backend=audit_backend,
        max_tokens=max_tokens,
        method="target_only_override",
        post_fix_violations=post_fix_violations,
        detected_rules=detected_rules,
    )


def _run_non_target_advisory_check(
    *,
    code: str,
    original_code: str | None,
    target_rule_id: str,
    detector_backend: InferenceBackend,
    audit_backend: InferenceBackend,
    max_tokens: int,
    override_denylist: set[str],
) -> ViolationRemovalResult:
    post_fix_violations = _detect_code(code, detector_backend)
    detected_rules = sorted({violation.rule_id for violation in post_fix_violations})
    detected_rule_set = set(detected_rules)

    if not post_fix_violations:
        return ViolationRemovalResult(
            removed=True,
            target_rule_id=target_rule_id,
            remaining_violations=[],
            method="non_target_advisory",
            reason="post-fix detector found no violations",
            post_fix_detected_rules=[],
            post_fix_detected_any=False,
            target_rule_detected=False,
            non_target_introduced=False,
            non_target_audit_blocking=False,
        )

    non_target_rules = sorted(detected_rule_set - {target_rule_id})
    if not non_target_rules:
        if target_rule_id in override_denylist:
            return _target_override_denied_result(
                method="non_target_advisory",
                target_rule_id=target_rule_id,
                post_fix_violations=post_fix_violations,
                detected_rules=detected_rules,
                reason=f"target-only override denied for {target_rule_id}",
            )
        if original_code is None:
            return _target_override_denied_result(
                method="non_target_advisory",
                target_rule_id=target_rule_id,
                post_fix_violations=post_fix_violations,
                detected_rules=detected_rules,
                reason="original target audit is required for target-only override",
            )
        return _run_target_override_audit(
            code=code,
            original_code=original_code,
            target_rule_id=target_rule_id,
            audit_backend=audit_backend,
            max_tokens=max_tokens,
            method="non_target_advisory",
            post_fix_violations=post_fix_violations,
            detected_rules=detected_rules,
        )

    if original_code is None:
        return ViolationRemovalResult(
            removed=False,
            target_rule_id=target_rule_id,
            remaining_violations=post_fix_violations,
            method="non_target_advisory",
            reason="original code is required for non-target introduced audit",
            post_fix_detected_rules=detected_rules,
            post_fix_detected_any=True,
            target_rule_detected=target_rule_id in detected_rule_set,
            non_target_introduced=None,
            non_target_audit_blocking=True,
        )

    audits = [
        _run_non_target_introduced_audit(
            original_code=original_code,
            fixed_code=code,
            non_target_rule_id=rule_id,
            target_rule_id=target_rule_id,
            backend=audit_backend,
            max_tokens=max_tokens,
        )
        for rule_id in non_target_rules
    ]
    introduced = any(audit.get("classification") == "introduced_by_fix" for audit in audits)
    uncertain = any(
        audit.get("classification") == "uncertain" or not bool(audit.get("parse_ok"))
        for audit in audits
    )
    if introduced or uncertain:
        reason = (
            "post-fix non-target violation introduced"
            if introduced
            else "post-fix non-target audit uncertain"
        )
        return ViolationRemovalResult(
            removed=False,
            target_rule_id=target_rule_id,
            remaining_violations=post_fix_violations,
            method="non_target_advisory",
            reason=reason,
            post_fix_detected_rules=detected_rules,
            post_fix_detected_any=True,
            target_rule_detected=target_rule_id in detected_rule_set,
            non_target_audits=audits,
            non_target_introduced=introduced,
            non_target_audit_blocking=True,
        )

    if target_rule_id in detected_rule_set:
        if target_rule_id in override_denylist:
            return _target_override_denied_result(
                method="non_target_advisory",
                target_rule_id=target_rule_id,
                post_fix_violations=post_fix_violations,
                detected_rules=detected_rules,
                reason=f"target-only override denied for {target_rule_id}",
                non_target_audits=audits,
            )
        return _run_target_override_audit(
            code=code,
            original_code=original_code,
            target_rule_id=target_rule_id,
            audit_backend=audit_backend,
            max_tokens=max_tokens,
            method="non_target_advisory",
            post_fix_violations=post_fix_violations,
            detected_rules=detected_rules,
            non_target_audits=audits,
        )

    return ViolationRemovalResult(
        removed=True,
        target_rule_id=target_rule_id,
        remaining_violations=[],
        method="non_target_advisory",
        reason="post-fix non-target detections recorded as advisory",
        post_fix_detected_rules=detected_rules,
        post_fix_detected_any=True,
        target_rule_detected=False,
        non_target_audits=audits,
        non_target_introduced=False,
        non_target_audit_blocking=False,
    )


def _run_target_override_audit(
    *,
    code: str,
    original_code: str,
    target_rule_id: str,
    audit_backend: InferenceBackend,
    max_tokens: int,
    method: str,
    post_fix_violations: list[Violation],
    detected_rules: list[str],
    non_target_audits: list[dict[str, object]] | None = None,
) -> ViolationRemovalResult:
    original_audit = _run_original_target_rule_audit(
        code=original_code,
        target_rule_id=target_rule_id,
        backend=audit_backend,
        max_tokens=max_tokens,
    )
    if not bool(original_audit["target_rule_present"]):
        return ViolationRemovalResult(
            removed=False,
            target_rule_id=target_rule_id,
            remaining_violations=post_fix_violations,
            method=method,
            confidence=str(original_audit["confidence"]),
            reason=str(original_audit["reason"]) or "original target rule not confirmed",
            raw_output=str(original_audit["raw_output"]),
            parse_ok=bool(original_audit["parse_ok"]),
            post_fix_detected_rules=detected_rules,
            post_fix_detected_any=True,
            target_rule_detected=True,
            original_target_present=False,
            original_target_confidence=str(original_audit["confidence"]),
            original_target_reason=str(original_audit["reason"]),
            original_target_evidence=str(original_audit["evidence"]),
            original_target_parse_ok=bool(original_audit["parse_ok"]),
            non_target_audits=non_target_audits or [],
            non_target_introduced=False if non_target_audits else None,
            non_target_audit_blocking=False if non_target_audits else None,
        )

    target_audit = _run_target_rule_audit_check(
        code=code,
        target_rule_id=target_rule_id,
        backend=audit_backend,
        max_tokens=max_tokens,
    )
    return ViolationRemovalResult(
        removed=target_audit.removed,
        target_rule_id=target_rule_id,
        remaining_violations=[] if target_audit.removed else post_fix_violations,
        method=method,
        confidence=target_audit.confidence,
        reason=target_audit.reason,
        remaining_evidence=target_audit.remaining_evidence,
        raw_output=target_audit.raw_output,
        parse_ok=target_audit.parse_ok,
        post_fix_detected_rules=detected_rules,
        post_fix_detected_any=True,
        target_rule_detected=True,
        override_applied=target_audit.removed,
        original_target_present=True,
        original_target_confidence=str(original_audit["confidence"]),
        original_target_reason=str(original_audit["reason"]),
        original_target_evidence=str(original_audit["evidence"]),
        original_target_parse_ok=bool(original_audit["parse_ok"]),
        non_target_audits=non_target_audits or [],
        non_target_introduced=False if non_target_audits else None,
        non_target_audit_blocking=False if non_target_audits else None,
    )


def _target_override_denied_result(
    *,
    method: str,
    target_rule_id: str,
    post_fix_violations: list[Violation],
    detected_rules: list[str],
    reason: str,
    non_target_audits: list[dict[str, object]] | None = None,
) -> ViolationRemovalResult:
    detected_rule_set = set(detected_rules)
    return ViolationRemovalResult(
        removed=False,
        target_rule_id=target_rule_id,
        remaining_violations=post_fix_violations,
        method=method,
        reason=reason,
        post_fix_detected_rules=detected_rules,
        post_fix_detected_any=True,
        target_rule_detected=target_rule_id in detected_rule_set,
        non_target_audits=non_target_audits or [],
        non_target_introduced=False if non_target_audits else None,
        non_target_audit_blocking=False if non_target_audits else None,
    )


def _run_target_rule_audit_check(
    *,
    code: str,
    target_rule_id: str,
    backend: InferenceBackend,
    max_tokens: int,
) -> ViolationRemovalResult:
    rule_info = _cert_rule_info(target_rule_id)
    prompt = VIOLATION_REMOVAL_AUDIT_PROMPT.format(
        rule_id=target_rule_id,
        rule_title=rule_info.get("title", "(unknown)"),
        rule_cue=rule_info.get("example", "(unknown)"),
        fixed_code=code,
    )
    output = backend.generate(prompt, max_tokens=max_tokens, temperature=0.0)
    parsed = parse_violation_removal_audit(output)
    removed = bool(parsed["target_violation_removed"])
    remaining: list[Violation] = []
    if not removed:
        remaining = [
            Violation(
                rule_id=target_rule_id,
                file_path="",
                line=1,
                column=1,
                message=str(parsed["reason"]) or "target violation may remain",
                severity=Severity.ERROR,
            )
        ]
    return ViolationRemovalResult(
        removed=removed,
        target_rule_id=target_rule_id,
        remaining_violations=remaining,
        method="target_rule_audit",
        confidence=str(parsed["confidence"]),
        reason=str(parsed["reason"]),
        remaining_evidence=str(parsed["remaining_evidence"]),
        raw_output=str(parsed["raw_output"]),
        parse_ok=bool(parsed["parse_ok"]),
    )


def _detect_code(
    code: str,
    backend: InferenceBackend,
    rules: list[str] | None = None,
) -> list[Violation]:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".c",
        prefix="certfix-validation-",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(code)
        temp_path = Path(f.name)
    try:
        return Detector(backend).check_file(temp_path, rules)
    finally:
        temp_path.unlink(missing_ok=True)


def _run_original_target_rule_audit(
    *,
    code: str,
    target_rule_id: str,
    backend: InferenceBackend,
    max_tokens: int,
) -> dict[str, object]:
    rule_info = _cert_rule_info(target_rule_id)
    prompt = ORIGINAL_TARGET_RULE_AUDIT_PROMPT.format(
        rule_id=target_rule_id,
        rule_title=rule_info.get("title", "(unknown)"),
        rule_cue=rule_info.get("example", "(unknown)"),
        original_code=code,
    )
    output = backend.generate(prompt, max_tokens=max_tokens, temperature=0.0)
    return parse_original_target_rule_audit(output)


def _run_non_target_introduced_audit(
    *,
    original_code: str,
    fixed_code: str,
    non_target_rule_id: str,
    target_rule_id: str,
    backend: InferenceBackend,
    max_tokens: int,
) -> dict[str, object]:
    rule_info = _cert_rule_info(non_target_rule_id)
    prompt = NON_TARGET_INTRODUCED_AUDIT_PROMPT.format(
        rule_id=non_target_rule_id,
        rule_title=rule_info.get("title", "(unknown)"),
        target_rule_id=target_rule_id,
        original_code=original_code,
        fixed_code=fixed_code,
    )
    output = backend.generate(prompt, max_tokens=max_tokens, temperature=0.0)
    parsed = parse_non_target_introduced_audit(output)
    parsed["rule_id"] = non_target_rule_id
    parsed["rule_title"] = rule_info.get("title", "")
    return parsed


def _cert_rule_info(rule_id: str) -> dict[str, str]:
    data_ref = resources.files("certfix.data").joinpath("cert_c_rules_with_examples.json")
    data = json.loads(data_ref.read_text(encoding="utf-8"))
    for category in data["categories"]:
        for rule in category["rules"]:
            if rule["id"] == rule_id:
                return {
                    "title": rule["title"],
                    "example": rule.get("example", ""),
                }
    return {}


def run_semantic_check(
    original_code: str,
    fixed_code: str,
    target_rule_id: str,
    backend: InferenceBackend,
    max_tokens: int = 1024,
) -> SemanticCheckResult:
    """Run the Stage 7 semantic validation gate."""
    prompt = SEMANTIC_CHECK_PROMPT.format(
        original_code=original_code,
        fixed_code=fixed_code,
        rule_id=target_rule_id,
    )
    if getattr(backend, "supports_grammar", False):
        generate_with_grammar = cast(Any, backend.generate)
        output = generate_with_grammar(
            prompt,
            max_tokens=max_tokens,
            temperature=0.1,
            grammar=SEMANTIC_CHECK_GRAMMAR,
        )
    else:
        output = backend.generate(prompt, max_tokens=max_tokens, temperature=0.1)
    return parse_semantic_check(output)


def run_semantic_auto_apply_check(
    original_code: str,
    fixed_code: str,
    target_rule_id: str,
    backend: InferenceBackend,
    max_tokens: int = 1024,
) -> SemanticAutoApplyResult:
    """Run the SPEC-style semantic auto-apply JSON gate."""
    prompt = SEMANTIC_AUTO_APPLY_PROMPT.format(
        original_code=original_code,
        fixed_code=fixed_code,
        rule_id=target_rule_id,
    )
    output = backend.generate(prompt, max_tokens=max_tokens, temperature=0.1)
    return parse_semantic_auto_apply_check(output)


def aggregate_final_status(
    compile_result: CompileCheckResult | None,
    removal_result: ViolationRemovalResult | None,
    semantic_result: SemanticCheckResult | None,
    fix_success: bool = True,
) -> FinalFixStatus:
    """Map validation gate results to the final apply status."""
    if not fix_success:
        return FinalFixStatus.UNRESOLVED

    if compile_result is None or semantic_result is None:
        return FinalFixStatus.MODEL_ERROR

    if not compile_result.ok:
        return FinalFixStatus.COMPILE_FAILED

    if removal_result is not None and not removal_result.removed:
        return FinalFixStatus.VIOLATION_REMAINING

    if semantic_result.target_violation_removed is False:
        return FinalFixStatus.VIOLATION_REMAINING

    if semantic_result.new_regression is True:
        return FinalFixStatus.REGRESSION_RISK

    if (
        semantic_result.verdict != SemanticVerdict.PASS
        or semantic_result.semantic_preserved is not True
        or semantic_result.target_violation_removed is not True
    ):
        return FinalFixStatus.SEMANTIC_RISK

    return FinalFixStatus.FIXED
