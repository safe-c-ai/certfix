"""Tests for models module."""

from certfix.models import (
    CheckResult,
    CompileCheckResult,
    FinalFixStatus,
    FixResult,
    RuleSelectionDecision,
    RuleSelectionResult,
    SemanticCheckResult,
    SemanticVerdict,
    Severity,
    Violation,
    ViolationRemovalResult,
)


class TestViolation:
    """Tests for Violation class."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        v = Violation(
            rule_id="EXP33-C",
            file_path="test.c",
            line=10,
            column=5,
            message="Uninitialized pointer",
            severity=Severity.ERROR,
        )

        d = v.to_dict()

        assert d["rule_id"] == "EXP33-C"
        assert d["file"] == "test.c"
        assert d["line"] == 10
        assert d["column"] == 5
        assert d["severity"] == "error"


class TestCheckResult:
    """Tests for CheckResult class."""

    def test_empty_result(self) -> None:
        """Test empty check result."""
        result = CheckResult(files_checked=5, violations=[])

        assert result.total_violations == 0
        assert not result.has_violations

    def test_with_violations(self) -> None:
        """Test check result with violations."""
        v = Violation(
            rule_id="EXP33-C",
            file_path="test.c",
            line=10,
            column=1,
            message="Test",
        )
        result = CheckResult(files_checked=1, violations=[v])

        assert result.total_violations == 1
        assert result.has_violations


class TestRuleSelectionResult:
    """Tests for RuleSelectionResult class."""

    def test_defaults(self) -> None:
        """Default optional fields should be empty."""
        result = RuleSelectionResult(decision=RuleSelectionDecision.UNRESOLVED)

        assert result.decision == RuleSelectionDecision.UNRESOLVED
        assert result.selected_rule_id is None
        assert result.selected_rank is None
        assert result.evidence == ""


class TestCompileCheckResult:
    """Tests for CompileCheckResult class."""

    def test_failure_result(self) -> None:
        """Compile failure data should be preserved."""
        result = CompileCheckResult(
            ok=False,
            command=["gcc", "-fsyntax-only", "test.c"],
            returncode=1,
            stderr="error",
        )

        assert result.ok is False
        assert result.returncode == 1
        assert result.stderr == "error"
        assert result.timed_out is False
        assert result.env_missing is False
        assert result.missing_headers == []
        assert result.unsupported_language is False
        assert result.unsupported_language_reason == ""


class TestViolationRemovalResult:
    """Tests for ViolationRemovalResult class."""

    def test_removed_result(self) -> None:
        """Removed result should preserve target rule."""
        result = ViolationRemovalResult(
            removed=True,
            target_rule_id="MEM30-C",
            remaining_violations=[],
        )

        assert result.removed is True
        assert result.target_rule_id == "MEM30-C"


class TestSemanticCheckResult:
    """Tests for SemanticCheckResult class."""

    def test_uncertain_result(self) -> None:
        """Semantic result should allow uncertain fields."""
        result = SemanticCheckResult(
            verdict=SemanticVerdict.UNCERTAIN,
            semantic_preserved=None,
            target_violation_removed=True,
            new_regression=None,
        )

        assert result.verdict == SemanticVerdict.UNCERTAIN
        assert result.semantic_preserved is None
        assert result.target_violation_removed is True
        assert FinalFixStatus.SEMANTIC_RISK.value == "semantic_risk"
        assert FinalFixStatus.COMPILE_ENV_MISSING.value == "compile_env_missing"
        assert FinalFixStatus.UNSUPPORTED_LANGUAGE.value == "unsupported_language"


class TestFixResult:
    """Tests for FixResult class."""

    def test_to_diff(self) -> None:
        """Test diff generation."""
        v = Violation(
            rule_id="EXP33-C",
            file_path="test.c",
            line=1,
            column=1,
            message="Test",
        )
        fix = FixResult(
            violation=v,
            original_code="int *p;\n*p = 1;",
            fixed_code="int *p = NULL;\nif (p) *p = 1;",
            success=True,
        )

        diff = fix.to_diff()

        assert "--- a/test.c" in diff
        assert "+++ b/test.c" in diff
        assert "-int *p;" in diff
        assert "+int *p = NULL;" in diff
