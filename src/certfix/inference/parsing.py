"""Shared parsing utilities for LLM-based inference backends."""

import json
import re

from certfix.models import (
    SemanticAutoApplyResult,
    SemanticCheckResult,
    SemanticVerdict,
    Severity,
    Violation,
)


def parse_violations(output: str, rules: list[str] | None = None) -> list[Violation]:
    """Parse LLM output for VIOLATION: <rule_id> at line <N>: <message> pattern.

    Args:
        output: Raw text output from LLM.
        rules: If provided, only keep violations whose rule_id is in this list.
            An empty list is treated as "keep all" (same as None).

    Returns:
        List of parsed Violation objects.
    """
    violations = []

    pattern = r"VIOLATION:\s*(\S+)\s+at\s+line\s+(\d+):\s*(.+)"

    for match in re.finditer(pattern, output, re.MULTILINE):
        rule_id = match.group(1)
        line = int(match.group(2))
        message = match.group(3).strip()

        if rules and rule_id not in rules:
            continue

        violations.append(
            Violation(
                rule_id=rule_id,
                file_path="",  # Will be set by caller
                line=line,
                column=1,
                message=message,
                severity=Severity.ERROR,
            )
        )

    return violations


def _parse_optional_field(output: str, field_name: str) -> str:
    match = re.search(rf"(?:^|>)\s*{field_name}:\s*(.+)", output, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_semantic_check(output: str) -> SemanticCheckResult:
    """Parse Stage 7 semantic validation output."""
    verdict_text = _parse_optional_field(output, "VERDICT").upper()
    verdict = _parse_semantic_verdict(verdict_text)
    reason = _parse_optional_field(output, "REASON")

    return SemanticCheckResult(
        verdict=verdict,
        semantic_preserved=_parse_optional_bool(output, "SEMANTIC_PRESERVED"),
        target_violation_removed=_parse_optional_bool(output, "TARGET_VIOLATION_REMOVED"),
        new_regression=_parse_optional_bool(output, "NEW_REGRESSION"),
        reason=reason,
        raw_output=output,
    )


def parse_semantic_auto_apply_check(output: str) -> SemanticAutoApplyResult:
    """Parse the structured semantic auto-apply JSON gate."""
    obj = _extract_json_object(output)
    if obj is None:
        return SemanticAutoApplyResult(
            parse_ok=False,
            auto_apply_ok=False,
            behavior_preserved=None,
            material_behavior_delta=None,
            uncertain_material_behavior=True,
            fail_type="parse_error",
            confidence="low",
            reason="semantic gate output was not valid JSON",
            raw_output=output,
        )

    required = {
        "parse_ok",
        "auto_apply_ok",
        "behavior_preserved",
        "material_behavior_delta",
        "uncertain_material_behavior",
        "fail_type",
        "confidence",
        "reason",
    }
    missing = sorted(required - set(obj))
    if missing:
        return SemanticAutoApplyResult(
            parse_ok=False,
            auto_apply_ok=False,
            behavior_preserved=None,
            material_behavior_delta=None,
            uncertain_material_behavior=True,
            fail_type="parse_error",
            confidence="low",
            reason=f"semantic gate JSON missing fields: {', '.join(missing)}",
            raw_output=output,
        )

    return SemanticAutoApplyResult(
        parse_ok=bool(obj.get("parse_ok")),
        auto_apply_ok=bool(obj.get("auto_apply_ok")),
        behavior_preserved=_json_bool(obj.get("behavior_preserved")),
        material_behavior_delta=_json_bool(obj.get("material_behavior_delta")),
        uncertain_material_behavior=_json_bool(obj.get("uncertain_material_behavior")),
        fail_type=str(obj.get("fail_type") or "unknown").strip().lower(),
        confidence=str(obj.get("confidence") or "low").strip().lower(),
        reason=str(obj.get("reason") or ""),
        raw_output=output,
    )


def parse_violation_removal_audit(output: str) -> dict[str, object]:
    """Parse the structured target violation-removal audit JSON."""
    obj = _extract_json_object(output)
    if obj is None:
        return {
            "parse_ok": False,
            "target_violation_removed": False,
            "confidence": "low",
            "reason": "violation-removal gate output was not valid JSON",
            "remaining_evidence": "",
            "raw_output": output,
        }

    required = {
        "parse_ok",
        "target_violation_removed",
        "confidence",
        "reason",
        "remaining_evidence",
    }
    missing = sorted(required - set(obj))
    if missing:
        return {
            "parse_ok": False,
            "target_violation_removed": False,
            "confidence": "low",
            "reason": f"violation-removal JSON missing fields: {', '.join(missing)}",
            "remaining_evidence": "",
            "raw_output": output,
        }

    removed = _json_bool(obj.get("target_violation_removed")) is True
    confidence = str(obj.get("confidence") or "low").strip().lower()
    remaining_evidence = str(obj.get("remaining_evidence") or "")
    if remaining_evidence.strip():
        removed = False
    if confidence == "low":
        removed = False

    return {
        "parse_ok": bool(obj.get("parse_ok")),
        "target_violation_removed": removed,
        "confidence": confidence,
        "reason": str(obj.get("reason") or ""),
        "remaining_evidence": remaining_evidence,
        "raw_output": output,
    }


def parse_original_target_rule_audit(output: str) -> dict[str, object]:
    """Parse the structured original target-rule presence audit JSON."""
    obj = _extract_json_object(output)
    if obj is None:
        return {
            "parse_ok": False,
            "target_rule_present": False,
            "confidence": "low",
            "reason": "original target audit output was not valid JSON",
            "evidence": "",
            "raw_output": output,
        }

    required = {
        "parse_ok",
        "target_rule_present",
        "confidence",
        "reason",
        "evidence",
    }
    missing = sorted(required - set(obj))
    if missing:
        return {
            "parse_ok": False,
            "target_rule_present": False,
            "confidence": "low",
            "reason": f"original target audit JSON missing fields: {', '.join(missing)}",
            "evidence": "",
            "raw_output": output,
        }

    confidence = str(obj.get("confidence") or "low").strip().lower()
    present = _json_bool(obj.get("target_rule_present")) is True
    if confidence == "low":
        present = False

    return {
        "parse_ok": bool(obj.get("parse_ok")),
        "target_rule_present": present,
        "confidence": confidence,
        "reason": str(obj.get("reason") or ""),
        "evidence": str(obj.get("evidence") or ""),
        "raw_output": output,
    }


def parse_non_target_introduced_audit(output: str) -> dict[str, object]:
    """Parse the structured non-target introduced-violation audit JSON."""
    obj = _extract_json_object(output)
    if obj is None:
        return _non_target_audit_parse_error(
            "non-target audit output was not valid JSON",
            output,
        )

    required = {
        "original_violation_present",
        "fixed_violation_present",
        "classification",
        "confidence",
        "evidence",
    }
    missing = sorted(required - set(obj))
    if missing:
        return _non_target_audit_parse_error(
            f"non-target audit JSON missing fields: {', '.join(missing)}",
            output,
        )

    original_present = _json_tri(obj.get("original_violation_present"))
    fixed_present = _json_tri(obj.get("fixed_violation_present"))
    classification = str(obj.get("classification") or "uncertain").strip().lower()
    confidence_value = obj.get("confidence")
    confidence = float(confidence_value) if isinstance(confidence_value, int | float) else 0.0
    allowed = {
        "introduced_by_fix",
        "preexisting_or_unrelated",
        "detector_false_positive",
        "removed_by_fix",
        "uncertain",
    }
    parse_ok = bool(obj.get("parse_ok", True))
    if (
        original_present == "invalid"
        or fixed_present == "invalid"
        or classification not in allowed
        or not 0.0 <= confidence <= 1.0
    ):
        return _non_target_audit_parse_error(
            "non-target audit JSON contained invalid field values",
            output,
        )
    if original_present == "uncertain" or fixed_present == "uncertain":
        classification = "uncertain"
    if confidence < 0.5:
        classification = "uncertain"

    return {
        "parse_ok": parse_ok,
        "original_violation_present": original_present,
        "fixed_violation_present": fixed_present,
        "classification": classification,
        "confidence": confidence,
        "evidence": str(obj.get("evidence") or ""),
        "raw_output": output,
    }


def _non_target_audit_parse_error(reason: str, output: str) -> dict[str, object]:
    return {
        "parse_ok": False,
        "original_violation_present": "uncertain",
        "fixed_violation_present": "uncertain",
        "classification": "uncertain",
        "confidence": 0.0,
        "evidence": reason,
        "raw_output": output,
    }


def _parse_semantic_verdict(value: str) -> SemanticVerdict:
    if value == "PASS":
        return SemanticVerdict.PASS
    if value == "FAIL":
        return SemanticVerdict.FAIL
    return SemanticVerdict.UNCERTAIN


def _parse_optional_bool(output: str, field_name: str) -> bool | None:
    value = _parse_optional_field(output, field_name).upper()
    if value == "YES":
        return True
    if value == "NO":
        return False
    return None


def _extract_json_object(text: str) -> dict[str, object] | None:
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(stripped[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _json_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes"}:
            return True
        if lowered in {"false", "no"}:
            return False
    return None


def _json_tri(value: object) -> bool | str:
    parsed = _json_bool(value)
    if parsed is not None:
        return parsed
    if isinstance(value, str) and value.strip().lower() == "uncertain":
        return "uncertain"
    return "invalid"


def extract_fixed_code(output: str) -> str:
    """Extract fixed C code from a model response.

    Prefer the first markdown code fence. If no fence is present, strip known
    model decision metadata and return the remaining text.
    """
    fence_match = re.search(r"```(?:c|C)?\s*\n(?P<code>.*?)\n?```", output, re.DOTALL)
    if fence_match:
        return fence_match.group("code").strip()

    lines = []
    for line in output.strip().splitlines():
        if re.match(r"^(DECISION|RULE|EVIDENCE):", line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()
