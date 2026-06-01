"""Unit tests for text output formatting."""

import io

from certfix.models import (
    CheckResult,
    CompileCheckResult,
    FinalFixStatus,
    FixResult,
    RuleCandidate,
    RuleSelectionDecision,
    RuleSelectionResult,
    SemanticCheckResult,
    SemanticVerdict,
    Severity,
    Violation,
    ViolationRemovalResult,
)
from certfix.output import TextFormatter


def _make_violation() -> Violation:
    return Violation(
        rule_id="MEM30-C",
        file_path="src/test.c",
        line=3,
        column=1,
        message="Use after free",
        severity=Severity.ERROR,
    )


def test_text_violations_include_candidates_and_selection() -> None:
    """Text check output should expose Stage 2/3 metadata."""
    violation = _make_violation()
    violation.candidates = [
        RuleCandidate("MEM30-C", 1, "Do not access freed memory"),
        RuleCandidate("MEM35-C", 2, "Allocate sufficient memory"),
    ]
    violation.rule_selection = RuleSelectionResult(
        decision=RuleSelectionDecision.APPLY_RULE,
        selected_rule_id="MEM30-C",
        selected_rank=1,
        evidence="p is used after free",
    )
    buf = io.StringIO()

    TextFormatter(buf).format_violations(CheckResult(files_checked=1, violations=[violation]))

    output = buf.getvalue()
    assert "src/test.c:3:1: [MEM30-C] Use after free" in output
    assert "candidates: 1:MEM30-C, 2:MEM35-C" in output
    assert "selector: apply_rule MEM30-C rank=1 - p is used after free" in output


def test_text_fixes_include_validation_summary() -> None:
    """Text fix output should summarize the Stage 5/6/7 gates."""
    violation = _make_violation()
    fix = FixResult(
        violation=violation,
        original_code="free(p);\nprintf(\"%s\", p);\n",
        fixed_code="printf(\"%s\", p);\nfree(p);\n",
        success=True,
        final_status=FinalFixStatus.FIXED,
        compile_result=CompileCheckResult(True, ["gcc", "-fsyntax-only"], 0),
        violation_removal_result=ViolationRemovalResult(True, "MEM30-C", []),
        semantic_result=SemanticCheckResult(
            verdict=SemanticVerdict.PASS,
            semantic_preserved=True,
            target_violation_removed=True,
            new_regression=False,
            reason="behavior preserved",
        ),
    )
    buf = io.StringIO()

    TextFormatter(buf).format_fixes([fix])

    output = buf.getvalue()
    assert "# Fixed MEM30-C at src/test.c:3 (fixed)" in output
    assert "# Validation:" in output
    assert "#   compile: pass" in output
    assert "#   violation_removal: pass target=MEM30-C remaining=0 method=detector" in output
    assert "#   semantic: pass" in output
    assert "behavior preserved" in output
