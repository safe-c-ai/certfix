"""Tests for shared violation parsing utility."""

from certfix.inference.parsing import (
    extract_fixed_code,
    parse_non_target_introduced_audit,
    parse_semantic_check,
    parse_violations,
)
from certfix.models import SemanticVerdict


class TestParseViolations:
    """Tests for parse_violations."""

    def test_single_violation(self) -> None:
        """Should parse a single VIOLATION line."""
        output = "VIOLATION: MEM30-C at line 5: Do not access freed memory"
        result = parse_violations(output)
        assert len(result) == 1
        assert result[0].rule_id == "MEM30-C"
        assert result[0].line == 5
        assert result[0].message == "Do not access freed memory"

    def test_multiple_violations(self) -> None:
        """Should parse multiple VIOLATION lines."""
        output = (
            "VIOLATION: MEM30-C at line 3: Do not access freed memory\n"
            "VIOLATION: EXP33-C at line 1: Do not read uninitialized memory"
        )
        result = parse_violations(output)
        assert len(result) == 2
        assert result[0].rule_id == "MEM30-C"
        assert result[0].line == 3
        assert result[1].rule_id == "EXP33-C"
        assert result[1].line == 1

    def test_no_violations(self) -> None:
        """NO_VIOLATIONS text should return empty list."""
        result = parse_violations("NO_VIOLATIONS")
        assert result == []

    def test_empty_string(self) -> None:
        """Empty string should return empty list."""
        result = parse_violations("")
        assert result == []

    def test_rule_filter_keep(self) -> None:
        """Should only keep violations matching the rule filter."""
        output = (
            "VIOLATION: MEM30-C at line 3: freed memory\n"
            "VIOLATION: EXP33-C at line 1: uninitialized memory"
        )
        result = parse_violations(output, rules=["MEM30-C"])
        assert len(result) == 1
        assert result[0].rule_id == "MEM30-C"

    def test_rule_filter_none_keeps_all(self) -> None:
        """rules=None should keep all violations."""
        output = (
            "VIOLATION: MEM30-C at line 3: freed memory\n"
            "VIOLATION: EXP33-C at line 1: uninitialized memory"
        )
        result = parse_violations(output, rules=None)
        assert len(result) == 2

    def test_rule_filter_empty_list_keeps_all(self) -> None:
        """rules=[] (falsy) should keep all violations."""
        output = (
            "VIOLATION: MEM30-C at line 3: freed memory\n"
            "VIOLATION: EXP33-C at line 1: uninitialized memory"
        )
        result = parse_violations(output, rules=[])
        assert len(result) == 2

    def test_mixed_content(self) -> None:
        """Should extract violations from mixed analysis text."""
        output = (
            "Analyzing the code for CERT-C violations...\n"
            "\n"
            "The code has the following issues:\n"
            "VIOLATION: MEM30-C at line 10: Use after free detected\n"
            "\n"
            "Additionally, there are style concerns.\n"
            "VIOLATION: STR31-C at line 25: Buffer overflow risk\n"
            "\n"
            "Summary: 2 violations found."
        )
        result = parse_violations(output)
        assert len(result) == 2
        assert result[0].rule_id == "MEM30-C"
        assert result[0].line == 10
        assert result[1].rule_id == "STR31-C"
        assert result[1].line == 25


class TestParseSemanticCheck:
    """Tests for parse_semantic_check."""

    def test_pass(self) -> None:
        """PASS output should parse all booleans."""
        output = (
            "VERDICT: PASS\n"
            "SEMANTIC_PRESERVED: YES\n"
            "TARGET_VIOLATION_REMOVED: YES\n"
            "NEW_REGRESSION: NO\n"
            "REASON: behavior preserved"
        )

        result = parse_semantic_check(output)

        assert result.verdict == SemanticVerdict.PASS
        assert result.semantic_preserved is True
        assert result.target_violation_removed is True
        assert result.new_regression is False
        assert result.reason == "behavior preserved"

    def test_fail(self) -> None:
        """FAIL output should parse negative fields."""
        output = (
            "VERDICT: FAIL\n"
            "SEMANTIC_PRESERVED: NO\n"
            "TARGET_VIOLATION_REMOVED: YES\n"
            "NEW_REGRESSION: YES\n"
            "REASON: removed required side effect"
        )

        result = parse_semantic_check(output)

        assert result.verdict == SemanticVerdict.FAIL
        assert result.semantic_preserved is False
        assert result.new_regression is True

    def test_missing_or_uncertain(self) -> None:
        """Missing or UNCERTAIN values should map to None/UNCERTAIN."""
        output = "VERDICT: MAYBE\nSEMANTIC_PRESERVED: UNCERTAIN"

        result = parse_semantic_check(output)

        assert result.verdict == SemanticVerdict.UNCERTAIN
        assert result.semantic_preserved is None
        assert result.target_violation_removed is None


class TestParseNonTargetIntroducedAudit:
    """Tests for non-target introduced audit JSON parsing."""

    def test_detector_false_positive(self) -> None:
        """Fixed-code false should keep detector false positives advisory."""
        result = parse_non_target_introduced_audit(
            '{"original_violation_present":false,"fixed_violation_present":false,'
            '"classification":"detector_false_positive","confidence":0.9,'
            '"evidence":"no dereference"}'
        )

        assert result["parse_ok"] is True
        assert result["classification"] == "detector_false_positive"
        assert result["fixed_violation_present"] is False

    def test_uncertain_when_judgment_uncertain(self) -> None:
        """Uncertain tri-state values should force uncertain classification."""
        result = parse_non_target_introduced_audit(
            '{"original_violation_present":"uncertain",'
            '"fixed_violation_present":true,'
            '"classification":"introduced_by_fix","confidence":0.8,'
            '"evidence":"context incomplete"}'
        )

        assert result["parse_ok"] is True
        assert result["classification"] == "uncertain"

    def test_invalid_json_fails_closed(self) -> None:
        """Invalid output should parse as a blocking uncertain audit."""
        result = parse_non_target_introduced_audit("not json")

        assert result["parse_ok"] is False
        assert result["classification"] == "uncertain"
        assert result["confidence"] == 0.0


class TestExtractFixedCode:
    """Tests for extracting fixed code from model output."""

    def test_extracts_code_fence(self) -> None:
        output = "Here is the fix:\n```c\nint x = 0;\n```\nDone."

        assert extract_fixed_code(output) == "int x = 0;"

    def test_removes_decision_metadata_without_fence(self) -> None:
        output = "DECISION: APPLY_RULE\nRULE: MEM30-C\nEVIDENCE: p is used after free\np = NULL;\n"

        assert extract_fixed_code(output) == "p = NULL;"
