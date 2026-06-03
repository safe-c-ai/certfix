"""Direct simple-mode repair flow."""

from __future__ import annotations

import re
from dataclasses import dataclass

from certfix.inference.base import InferenceBackend
from certfix.inference.parsing import extract_fixed_code
from certfix.models import FinalFixStatus, FixResult, Severity, Violation
from certfix.prompt_profiles import RepairOutputMode, resolve_repair_profile
from certfix.prompts import build_simple_repair_prompt


@dataclass
class SimpleRepairDecision:
    """Parsed direct-repair model output."""

    decision: str
    rule_id: str | None = None
    line: int = 1
    evidence: str = ""
    fixed_code: str = ""
    raw_output: str = ""


def run_simple_repair(
    code: str,
    file_path: str,
    backend: InferenceBackend,
    rules: list[str] | None = None,
    max_tokens: int = 4096,
    prompt_profile: str | None = None,
) -> FixResult | None:
    """Run a direct detect-and-fix pass for one complete source file."""
    profile = resolve_repair_profile(prompt_profile)
    prompt = build_simple_repair_prompt(code, rules, profile.name)
    output = backend.generate(prompt, max_tokens=max_tokens, temperature=profile.temperature)
    if profile.output_mode == RepairOutputMode.CODE_ONLY:
        decision = parse_code_only_repair(output, code, _target_rule_id(rules))
    else:
        decision = parse_simple_repair(output)

    if decision.decision == "NO_VIOLATIONS":
        return None

    violation = Violation(
        rule_id=decision.rule_id or "UNKNOWN",
        file_path=file_path,
        line=decision.line,
        column=1,
        message=decision.evidence or "Simple mode did not provide evidence",
        severity=Severity.ERROR,
    )

    if decision.decision != "APPLY_FIX":
        return FixResult(
            violation=violation,
            original_code=code,
            fixed_code=code,
            success=False,
            error_message=decision.evidence or f"Simple mode decision: {decision.decision}",
            final_status=FinalFixStatus.UNRESOLVED,
        )

    if _is_placeholder_code(decision.fixed_code):
        decision.fixed_code = ""

    if not decision.rule_id or not decision.fixed_code:
        return FixResult(
            violation=violation,
            original_code=code,
            fixed_code=code,
            success=False,
            error_message="Simple mode output was missing RULE or fixed code",
            final_status=FinalFixStatus.MODEL_ERROR,
        )

    return FixResult(
        violation=violation,
        original_code=code,
        fixed_code=decision.fixed_code,
        success=True,
    )


def parse_simple_repair(output: str) -> SimpleRepairDecision:
    """Parse simple direct-repair output."""
    decision = _field(output, "DECISION").upper()
    if decision == "NO_VIOLATIONS":
        return SimpleRepairDecision(decision=decision, raw_output=output)
    if decision not in {"APPLY_FIX", "UNRESOLVED"}:
        return SimpleRepairDecision(
            decision="UNRESOLVED",
            evidence="Missing or unknown DECISION line",
            raw_output=output,
        )

    line_text = _field(output, "LINE")
    line = int(line_text) if line_text.isdigit() else 1
    fixed_code = (
        _strip_c_comments(_extract_simple_fixed_code(output)) if decision == "APPLY_FIX" else ""
    )
    return SimpleRepairDecision(
        decision=decision,
        rule_id=_field(output, "RULE") or None,
        line=line,
        evidence=_field(output, "EVIDENCE"),
        fixed_code=fixed_code,
        raw_output=output,
    )


def parse_code_only_repair(
    output: str,
    original_code: str,
    rule_id: str | None = None,
) -> SimpleRepairDecision:
    """Parse a code-only repair model output."""
    fixed_code = _strip_c_comments(_extract_simple_fixed_code(output))
    if _is_placeholder_code(fixed_code):
        fixed_code = ""

    if not fixed_code:
        return SimpleRepairDecision(
            decision="UNRESOLVED",
            rule_id=rule_id,
            evidence="Code-only repair output did not contain C code",
            raw_output=output,
        )

    if fixed_code.strip() == _strip_c_comments(original_code).strip():
        return SimpleRepairDecision(
            decision="NO_VIOLATIONS",
            rule_id=rule_id,
            evidence="Code-only repair output was unchanged",
            raw_output=output,
        )

    return SimpleRepairDecision(
        decision="APPLY_FIX",
        rule_id=rule_id,
        line=1,
        evidence="Code-only simple repair produced a changed candidate",
        fixed_code=fixed_code,
        raw_output=output,
    )


def _target_rule_id(rules: list[str] | None) -> str | None:
    return rules[0] if rules and len(rules) == 1 else None


def _field(output: str, name: str) -> str:
    match = re.search(rf"(?:^|>)\s*{name}:\s*(.+)", output, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_simple_fixed_code(output: str) -> str:
    """Extract the final fenced code block from direct-repair output."""
    matches = list(re.finditer(r"```(?:c|C)?\s*\n(?P<code>.*?)\n?```", output, re.DOTALL))
    if matches:
        for match in reversed(matches):
            code = match.group("code").strip()
            if not _is_placeholder_code(code):
                return code
        return ""
    return str(extract_fixed_code(output))


def _is_placeholder_code(code: str) -> bool:
    stripped = code.strip()
    return not stripped or stripped.startswith("<") or "complete fixed C source file" in stripped


def _strip_c_comments(code: str) -> str:
    """Remove C comments without treating comment markers inside strings as comments."""
    result: list[str] = []
    i = 0
    state = "normal"

    while i < len(code):
        ch = code[i]
        nxt = code[i + 1] if i + 1 < len(code) else ""

        if state == "normal":
            if ch == "/" and nxt == "/":
                _append_separator_space(result)
                state = "line_comment"
                i += 2
                continue
            if ch == "/" and nxt == "*":
                _append_separator_space(result)
                state = "block_comment"
                i += 2
                continue
            if ch == '"':
                state = "string"
            elif ch == "'":
                state = "char"
            result.append(ch)
            i += 1
            continue

        if state == "string":
            result.append(ch)
            if ch == "\\" and nxt:
                result.append(nxt)
                i += 2
                continue
            if ch == '"':
                state = "normal"
            i += 1
            continue

        if state == "char":
            result.append(ch)
            if ch == "\\" and nxt:
                result.append(nxt)
                i += 2
                continue
            if ch == "'":
                state = "normal"
            i += 1
            continue

        if state == "line_comment":
            if ch == "\n":
                result.append(ch)
                state = "normal"
            i += 1
            continue

        if state == "block_comment":
            if ch == "\n":
                result.append(ch)
                i += 1
                continue
            if ch == "*" and nxt == "/":
                state = "normal"
                i += 2
                continue
            i += 1
            continue

    return "\n".join(line.rstrip() for line in "".join(result).splitlines()).strip()


def strip_c_comments(code: str) -> str:
    """Public helper for removing C comments before LLM-facing repair steps."""
    return _strip_c_comments(code)


def _append_separator_space(result: list[str]) -> None:
    if result and not result[-1].isspace():
        result.append(" ")
