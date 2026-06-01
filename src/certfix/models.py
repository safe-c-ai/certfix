"""Data models for certfix."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class RuleCandidate:
    """A candidate CERT-C rule from Top-K detection."""

    rule_id: str
    rank: int
    description: str = ""


class Severity(Enum):
    """Violation severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RuleSelectionDecision(Enum):
    """Rule selection decisions."""

    APPLY_RULE = "apply_rule"
    NO_VIOLATIONS = "no_violations"
    UNRESOLVED = "unresolved"


@dataclass
class RuleSelectionResult:
    """Result of selecting one rule from Top-K candidates."""

    decision: RuleSelectionDecision
    selected_rule_id: str | None = None
    selected_rank: int | None = None
    evidence: str = ""
    raw_output: str = ""


@dataclass
class CompileCheckResult:
    """Result of the Stage 5 compile validation gate."""

    ok: bool
    command: list[str]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    env_missing: bool = False
    missing_headers: list[str] = field(default_factory=list)
    unsupported_language: bool = False
    unsupported_language_reason: str = ""


@dataclass
class ViolationRemovalResult:
    """Result of the Stage 6 violation removal gate."""

    removed: bool
    target_rule_id: str
    remaining_violations: list["Violation"]
    method: str = "detector"
    confidence: str = ""
    reason: str = ""
    remaining_evidence: str = ""
    raw_output: str = ""
    parse_ok: bool | None = None
    post_fix_detected_rules: list[str] = field(default_factory=list)
    post_fix_detected_any: bool | None = None
    target_rule_detected: bool | None = None
    override_applied: bool = False
    original_target_present: bool | None = None
    original_target_confidence: str = ""
    original_target_reason: str = ""
    original_target_evidence: str = ""
    original_target_parse_ok: bool | None = None
    non_target_audits: list[dict[str, object]] = field(default_factory=list)
    non_target_introduced: bool | None = None
    non_target_audit_blocking: bool | None = None


class SemanticVerdict(Enum):
    """Stage 7 semantic validation verdicts."""

    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


@dataclass
class SemanticCheckResult:
    """Result of the Stage 7 semantic validation gate."""

    verdict: SemanticVerdict
    semantic_preserved: bool | None
    target_violation_removed: bool | None
    new_regression: bool | None
    reason: str = ""
    raw_output: str = ""


@dataclass(frozen=True)
class ProgrammaticFinding:
    """A conservative structural finding that blocks automatic fix application."""

    check_id: str
    rule_id: str
    verdict: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "rule_id": self.rule_id,
            "verdict": self.verdict,
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass
class SemanticAutoApplyResult:
    """Structured semantic auto-apply gate result."""

    parse_ok: bool
    auto_apply_ok: bool
    behavior_preserved: bool | None
    material_behavior_delta: bool | None
    uncertain_material_behavior: bool | None
    fail_type: str
    confidence: str
    reason: str = ""
    raw_output: str = ""

    @property
    def semantic_ok(self) -> bool:
        return (
            self.parse_ok
            and self.auto_apply_ok
            and self.behavior_preserved is True
            and self.material_behavior_delta is False
            and self.uncertain_material_behavior is False
            and self.fail_type == "none"
            and self.confidence != "low"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "parse_ok": self.parse_ok,
            "auto_apply_ok": self.auto_apply_ok,
            "behavior_preserved": self.behavior_preserved,
            "material_behavior_delta": self.material_behavior_delta,
            "uncertain_material_behavior": self.uncertain_material_behavior,
            "fail_type": self.fail_type,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class FixValidationCategory(Enum):
    """SPEC-compatible fix validator category."""

    PASS = "pass"
    FORMAT_ERROR = "format_error"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    COMPILE_ENV_MISSING = "compile_env_missing"
    COMPILE_ERROR = "compile_error"
    VIOLATION_REMAINS = "violation_remains"
    PROGRAMMATIC_CHECK_FAILED = "programmatic_check_failed"
    SEMANTIC_CHANGED = "semantic_changed"
    REGRESSION_INTRODUCED = "regression_introduced"
    OVER_DELETION = "over_deletion"
    MANUAL_BOUNDARY = "manual_boundary"


@dataclass
class FixValidatorResult:
    """Unified post-generation validation result for auto-apply and retry."""

    auto_apply_ok: bool
    category: FixValidationCategory
    retryable: bool
    details: str
    format_ok: bool
    compile_ok: bool
    violation_removed: bool
    semantic_ok: bool
    regression_free: bool
    programmatic_findings: list[ProgrammaticFinding] = field(default_factory=list)
    compiler_stderr: str = ""
    semantic_check_result: SemanticAutoApplyResult | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "auto_apply_ok": self.auto_apply_ok,
            "category": self.category.value,
            "retryable": self.retryable,
            "details": self.details,
            "format_ok": self.format_ok,
            "compile_ok": self.compile_ok,
            "violation_removed": self.violation_removed,
            "semantic_ok": self.semantic_ok,
            "regression_free": self.regression_free,
            "programmatic_findings": [finding.to_dict() for finding in self.programmatic_findings],
            "compiler_stderr": self.compiler_stderr,
            "semantic_check_result": self.semantic_check_result.to_dict()
            if self.semantic_check_result
            else None,
        }


class FinalFixStatus(Enum):
    """Final status for a proposed fix."""

    FIXED = "fixed"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    COMPILE_ENV_MISSING = "compile_env_missing"
    COMPILE_FAILED = "compile_failed"
    VIOLATION_REMAINING = "violation_remaining"
    SEMANTIC_RISK = "semantic_risk"
    REGRESSION_RISK = "regression_risk"
    UNRESOLVED = "unresolved"
    MODEL_ERROR = "model_error"


@dataclass
class Violation:
    """A detected CERT-C violation."""

    rule_id: str
    file_path: str
    line: int
    column: int
    message: str
    severity: Severity = Severity.ERROR
    code_snippet: str | None = None
    candidates: list[RuleCandidate] | None = None
    rule_selection: RuleSelectionResult | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON output."""
        data: dict[str, object] = {
            "rule_id": self.rule_id,
            "file": self.file_path,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "severity": self.severity.value,
        }
        if self.candidates:
            data["candidates"] = [
                {
                    "rule_id": c.rule_id,
                    "rank": c.rank,
                    "description": c.description,
                }
                for c in self.candidates
            ]
        if self.rule_selection:
            data["selector_decision"] = self.rule_selection.decision.value
            data["selected_rank"] = self.rule_selection.selected_rank
            data["selector_evidence"] = self.rule_selection.evidence
        return data


@dataclass
class FixResult:
    """Result of a fix operation."""

    violation: Violation
    original_code: str
    fixed_code: str
    success: bool
    error_message: str | None = None
    compile_result: CompileCheckResult | None = None
    violation_removal_result: ViolationRemovalResult | None = None
    semantic_result: SemanticCheckResult | None = None
    validator_result: FixValidatorResult | None = None
    final_status: FinalFixStatus | None = None
    timings: dict[str, float] = field(default_factory=dict)
    source: str | None = None
    retry_count: int = 0
    retry_metadata: dict[str, object] = field(default_factory=dict)

    def to_diff(self) -> str:
        """Generate unified diff."""
        import difflib

        original_lines = self.original_code.splitlines(keepends=True)
        fixed_lines = self.fixed_code.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"a/{self.violation.file_path}",
            tofile=f"b/{self.violation.file_path}",
        )
        return "".join(diff)


@dataclass
class CheckResult:
    """Result of a check operation."""

    files_checked: int
    violations: list[Violation]

    @property
    def total_violations(self) -> int:
        """Total number of violations."""
        return len(self.violations)

    @property
    def has_violations(self) -> bool:
        """Whether any violations were found."""
        return len(self.violations) > 0
