"""Tests for validation gates."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from certfix.config import CompileValidationConfig
from certfix.core.validation import (
    aggregate_final_status,
    run_compile_check,
    run_semantic_auto_apply_check,
    run_semantic_check,
    run_violation_removal_check,
)
from certfix.inference.base import InferenceBackend
from certfix.models import (
    CompileCheckResult,
    FinalFixStatus,
    SemanticCheckResult,
    SemanticVerdict,
    Severity,
    Violation,
    ViolationRemovalResult,
)


class FakeValidationBackend(InferenceBackend):
    """Backend stub for validation gate tests."""

    def __init__(
        self,
        violations: list[Violation] | None = None,
        generated: str | list[str] = "",
    ) -> None:
        self.violations = violations or []
        self.generated = [generated] if isinstance(generated, str) else list(generated)
        self.last_rules: list[str] | None = None
        self.last_prompt = ""
        self.last_grammar: str | None = None
        self.generate_calls = 0

    def detect(self, code: str, rules: list[str] | None = None) -> list[Violation]:
        self.last_rules = rules
        return self.violations

    def fix(self, code: str, violation: Violation) -> str:
        return code

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        stop: list[str] | None = None,
    ) -> str:
        self.last_prompt = prompt
        self.generate_calls += 1
        if self.generate_calls <= len(self.generated):
            return self.generated[self.generate_calls - 1]
        return self.generated[-1] if self.generated else ""


class FakeGrammarValidationBackend(FakeValidationBackend):
    """Backend stub that accepts grammar-constrained generation."""

    supports_grammar = True

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        stop: list[str] | None = None,
        grammar: str | None = None,
    ) -> str:
        self.last_prompt = prompt
        self.last_grammar = grammar
        self.generate_calls += 1
        if self.generate_calls <= len(self.generated):
            return self.generated[self.generate_calls - 1]
        return self.generated[-1] if self.generated else ""


def test_run_compile_check_success() -> None:
    """Successful compiler result should set ok=True."""
    completed = subprocess.CompletedProcess(
        args=["clang"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with patch("certfix.core.validation.subprocess.run", return_value=completed) as mock_run:
        result = run_compile_check(
            "int main(void) { return 0; }",
            CompileValidationConfig(command="clang", args=["-fsyntax-only"], timeout=45),
        )

    assert result.ok is True
    assert result.returncode == 0
    assert result.timed_out is False
    assert result.command[0] == "clang"
    assert result.command[1] == "-fsyntax-only"
    assert result.command[-1].endswith(".c")
    assert not Path(result.command[-1]).exists()
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["timeout"] == 45
    assert mock_run.call_args.kwargs["check"] is False


def test_run_compile_check_adds_include_paths() -> None:
    """Configured include paths should be passed to the compiler."""
    completed = subprocess.CompletedProcess(
        args=["gcc"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with patch("certfix.core.validation.subprocess.run", return_value=completed):
        result = run_compile_check(
            "int main(void) { return 0; }",
            CompileValidationConfig(include_paths=["tests/support", "third_party/include"]),
        )

    assert result.ok is True
    assert result.command[-5:-1] == ["-I", "tests/support", "-I", "third_party/include"]


def test_run_compile_check_failure() -> None:
    """Compiler errors should be preserved in the result."""
    completed = subprocess.CompletedProcess(
        args=["gcc"],
        returncode=1,
        stdout="",
        stderr="syntax error",
    )

    with patch("certfix.core.validation.subprocess.run", return_value=completed):
        result = run_compile_check("int main(")

    assert result.ok is False
    assert result.returncode == 1
    assert result.stderr == "syntax error"


def test_run_compile_check_classifies_missing_header() -> None:
    """Missing headers should be classified as compile environment issues."""
    completed = subprocess.CompletedProcess(
        args=["gcc"],
        returncode=1,
        stdout="",
        stderr=(
            '/tmp/x.c:1:10: fatal error: std_testcase.h: No such file or directory\n'
            '    1 | #include "std_testcase.h"\n'
        ),
    )

    with patch("certfix.core.validation.subprocess.run", return_value=completed):
        result = run_compile_check('#include "std_testcase.h"\n')

    assert result.ok is False
    assert result.env_missing is True
    assert result.missing_headers == ["std_testcase.h"]


def test_run_compile_check_classifies_cpp_syntax_as_unsupported_language() -> None:
    """C++ syntax should be excluded from C-only compile failures."""
    completed = subprocess.CompletedProcess(
        args=["gcc"],
        returncode=1,
        stdout="",
        stderr=(
            "/tmp/x.c:3:1: error: unknown type name 'namespace'\n"
            "/tmp/x.c:8:12: error: 'new' undeclared\n"
        ),
    )

    with patch("certfix.core.validation.subprocess.run", return_value=completed):
        result = run_compile_check("namespace N { int *p = new int; }\n")

    assert result.ok is False
    assert result.unsupported_language is True
    assert result.unsupported_language_reason == "C++ namespace syntax used in C-only mode"


def test_run_compile_check_classifies_cpp_header_as_unsupported_language() -> None:
    """C++ standard library headers are unsupported in the C-only release path."""
    completed = subprocess.CompletedProcess(
        args=["gcc"],
        returncode=1,
        stdout="",
        stderr="/tmp/x.c:1:10: fatal error: vector: No such file or directory\n",
    )

    with patch("certfix.core.validation.subprocess.run", return_value=completed):
        result = run_compile_check("#include <vector>\n")

    assert result.ok is False
    assert result.env_missing is True
    assert result.unsupported_language is True
    assert result.missing_headers == ["vector"]
    assert result.unsupported_language_reason == (
        "C++ standard library header used in C-only mode"
    )


def test_run_compile_check_timeout() -> None:
    """Compiler timeout should produce a timed_out result."""
    timeout = subprocess.TimeoutExpired(
        cmd=["gcc"],
        timeout=1,
        output="partial out",
        stderr="partial err",
    )

    with patch("certfix.core.validation.subprocess.run", side_effect=timeout):
        result = run_compile_check("int main(void) { return 0; }")

    assert result.ok is False
    assert result.returncode is None
    assert result.stdout == "partial out"
    assert result.stderr == "partial err"
    assert result.timed_out is True
    assert not Path(result.command[-1]).exists()


def test_run_violation_removal_check_removed() -> None:
    """No target-rule detections should pass Stage 6."""
    backend = FakeValidationBackend()

    result = run_violation_removal_check("int main(void) { return 0; }", "MEM30-C", backend)

    assert result.removed is True
    assert result.remaining_violations == []
    assert backend.last_rules == ["MEM30-C"]


def test_run_violation_removal_check_remaining() -> None:
    """Remaining target-rule detections should fail Stage 6."""
    violation = Violation(
        rule_id="MEM30-C",
        file_path="",
        line=1,
        column=1,
        message="still present",
        severity=Severity.ERROR,
    )
    backend = FakeValidationBackend(violations=[violation])

    result = run_violation_removal_check("bad code", "MEM30-C", backend)

    assert result.removed is False
    assert result.remaining_violations == [violation]


def test_run_violation_removal_check_target_rule_audit_removed() -> None:
    """Target-rule audit should accept a fixed code when the rule is removed."""
    backend = FakeValidationBackend(
        generated=(
            '{"parse_ok":true,"target_violation_removed":true,'
            '"confidence":"high","reason":"target use-after-free removed",'
            '"remaining_evidence":""}'
        )
    )

    result = run_violation_removal_check(
        "free(p);",
        "MEM30-C",
        backend,
        method="target_rule_audit",
    )

    assert result.removed is True
    assert result.method == "target_rule_audit"
    assert result.confidence == "high"
    assert result.remaining_violations == []
    assert "Do not access freed memory" in backend.last_prompt


def test_run_violation_removal_check_target_rule_audit_remaining() -> None:
    """Target-rule audit should fail when specific remaining evidence is present."""
    backend = FakeValidationBackend(
        generated=(
            '{"parse_ok":true,"target_violation_removed":true,'
            '"confidence":"high","reason":"inconsistent",'
            '"remaining_evidence":"printf(p) after free(p)"}'
        )
    )

    result = run_violation_removal_check(
        'free(p); printf("%s", p);',
        "MEM30-C",
        backend,
        method="target_rule_audit",
    )

    assert result.removed is False
    assert result.remaining_evidence == "printf(p) after free(p)"
    assert len(result.remaining_violations) == 1


def test_target_only_override_passes_when_post_fix_scan_is_clean() -> None:
    """A clean whole-code post-fix scan should pass without audit override."""
    detector = FakeValidationBackend()
    audit = FakeValidationBackend(generated='{"unexpected": true}')

    result = run_violation_removal_check(
        "int main(void) { return 0; }",
        "MEM30-C",
        detector,
        method="target_only_override",
        audit_backend=audit,
        original_code='free(p); printf("%s", p);',
    )

    assert result.removed is True
    assert result.method == "target_only_override"
    assert result.reason == "post-fix detector found no violations"
    assert result.post_fix_detected_rules == []
    assert audit.generate_calls == 0


def test_target_only_override_blocks_non_target_post_fix_detection() -> None:
    """Non-target post-fix detections must not be overridden by target audit."""
    non_target = Violation(
        rule_id="EXP34-C",
        file_path="",
        line=1,
        column=1,
        message="null dereference",
        severity=Severity.ERROR,
    )
    detector = FakeValidationBackend(violations=[non_target])
    audit = FakeValidationBackend(
        generated=(
            '{"parse_ok":true,"target_rule_present":true,"confidence":"high",'
            '"reason":"present","evidence":"free then use"}'
        )
    )

    result = run_violation_removal_check(
        "bad code",
        "MEM30-C",
        detector,
        method="target_only_override",
        audit_backend=audit,
        original_code='free(p); printf("%s", p);',
    )

    assert result.removed is False
    assert result.reason == "post-fix detector found non-target violations"
    assert result.post_fix_detected_rules == ["EXP34-C"]
    assert audit.generate_calls == 0


def test_target_only_override_requires_original_target_confirmation() -> None:
    """Target-only override should fail when original target audit is false."""
    target = Violation(
        rule_id="MEM30-C",
        file_path="",
        line=1,
        column=1,
        message="target remains",
        severity=Severity.ERROR,
    )
    detector = FakeValidationBackend(violations=[target])
    audit = FakeValidationBackend(
        generated=(
            '{"parse_ok":true,"target_rule_present":false,"confidence":"high",'
            '"reason":"original is already safe","evidence":""}'
        )
    )

    result = run_violation_removal_check(
        "fixed code",
        "MEM30-C",
        detector,
        method="target_only_override",
        audit_backend=audit,
        original_code="safe code",
    )

    assert result.removed is False
    assert result.original_target_present is False
    assert result.override_applied is False
    assert audit.generate_calls == 1


def test_target_only_override_applies_when_original_and_fixed_audits_pass() -> None:
    """Target-only detector false positives can be overridden after both audits."""
    target = Violation(
        rule_id="MEM30-C",
        file_path="",
        line=1,
        column=1,
        message="target remains",
        severity=Severity.ERROR,
    )
    detector = FakeValidationBackend(violations=[target])
    audit = FakeValidationBackend(
        generated=[
            (
                '{"parse_ok":true,"target_rule_present":true,"confidence":"high",'
                '"reason":"original uses p after free","evidence":"printf(p) after free"}'
            ),
            (
                '{"parse_ok":true,"target_violation_removed":true,'
                '"confidence":"high","reason":"target use-after-free removed",'
                '"remaining_evidence":""}'
            ),
        ]
    )

    result = run_violation_removal_check(
        "free(p);",
        "MEM30-C",
        detector,
        method="target_only_override",
        audit_backend=audit,
        original_code='free(p); printf("%s", p);',
    )

    assert result.removed is True
    assert result.override_applied is True
    assert result.original_target_present is True
    assert result.post_fix_detected_rules == ["MEM30-C"]
    assert audit.generate_calls == 2


def test_target_only_override_respects_temporary_denylist() -> None:
    """Known risky rules should not be overridden until rule checks improve."""
    target = Violation(
        rule_id="STR31-C",
        file_path="",
        line=1,
        column=1,
        message="target remains",
        severity=Severity.ERROR,
    )
    detector = FakeValidationBackend(violations=[target])
    audit = FakeValidationBackend()

    result = run_violation_removal_check(
        "fixed code",
        "STR31-C",
        detector,
        method="target_only_override",
        audit_backend=audit,
        original_code="original code",
    )

    assert result.removed is False
    assert result.reason == "target-only override denied for STR31-C"
    assert audit.generate_calls == 0


def test_non_target_advisory_passes_detector_false_positive() -> None:
    """Non-target detector false positives should become advisory telemetry."""
    non_target = Violation(
        rule_id="EXP34-C",
        file_path="",
        line=1,
        column=1,
        message="null dereference",
        severity=Severity.ERROR,
    )
    detector = FakeValidationBackend(violations=[non_target])
    audit = FakeValidationBackend(
        generated=(
            '{"original_violation_present":false,"fixed_violation_present":false,'
            '"classification":"detector_false_positive","confidence":0.9,'
            '"evidence":"fixed code checks p before dereference"}'
        )
    )

    result = run_violation_removal_check(
        "if (p) return *p;",
        "MEM30-C",
        detector,
        method="non_target_advisory",
        audit_backend=audit,
        original_code='free(p); printf("%s", p);',
    )

    assert result.removed is True
    assert result.method == "non_target_advisory"
    assert result.reason == "post-fix non-target detections recorded as advisory"
    assert result.post_fix_detected_rules == ["EXP34-C"]
    assert result.non_target_introduced is False
    assert result.non_target_audit_blocking is False
    assert result.non_target_audits[0]["classification"] == "detector_false_positive"


def test_non_target_advisory_blocks_introduced_non_target_violation() -> None:
    """Confirmed introduced non-target violations should block auto-apply."""
    non_target = Violation(
        rule_id="MEM31-C",
        file_path="",
        line=1,
        column=1,
        message="memory leak",
        severity=Severity.ERROR,
    )
    detector = FakeValidationBackend(violations=[non_target])
    audit = FakeValidationBackend(
        generated=(
            '{"original_violation_present":false,"fixed_violation_present":true,'
            '"classification":"introduced_by_fix","confidence":0.95,'
            '"evidence":"fixed code calls strdup without a free path"}'
        )
    )

    result = run_violation_removal_check(
        "char *p = strdup(s); return p;",
        "DCL30-C",
        detector,
        method="non_target_advisory",
        audit_backend=audit,
        original_code="return s;",
    )

    assert result.removed is False
    assert result.reason == "post-fix non-target violation introduced"
    assert result.non_target_introduced is True
    assert result.non_target_audit_blocking is True


def test_non_target_advisory_blocks_uncertain_non_target_audit() -> None:
    """Uncertain non-target audits should fail closed."""
    non_target = Violation(
        rule_id="EXP34-C",
        file_path="",
        line=1,
        column=1,
        message="null dereference",
        severity=Severity.ERROR,
    )
    detector = FakeValidationBackend(violations=[non_target])
    audit = FakeValidationBackend(
        generated=(
            '{"original_violation_present":"uncertain",'
            '"fixed_violation_present":"uncertain",'
            '"classification":"uncertain","confidence":0.2,'
            '"evidence":"insufficient context"}'
        )
    )

    result = run_violation_removal_check(
        "return *p;",
        "MEM30-C",
        detector,
        method="non_target_advisory",
        audit_backend=audit,
        original_code="return 0;",
    )

    assert result.removed is False
    assert result.reason == "post-fix non-target audit uncertain"
    assert result.non_target_audit_blocking is True


def test_non_target_advisory_allows_target_audit_after_non_target_advisory() -> None:
    """Target detections still require target-rule audit when non-targets are advisory."""
    target = Violation(
        rule_id="MEM30-C",
        file_path="",
        line=1,
        column=1,
        message="target remains",
        severity=Severity.ERROR,
    )
    non_target = Violation(
        rule_id="EXP34-C",
        file_path="",
        line=1,
        column=1,
        message="null dereference",
        severity=Severity.ERROR,
    )
    detector = FakeValidationBackend(violations=[target, non_target])
    audit = FakeValidationBackend(
        generated=[
            (
                '{"original_violation_present":false,"fixed_violation_present":false,'
                '"classification":"detector_false_positive","confidence":0.9,'
                '"evidence":"no null dereference"}'
            ),
            (
                '{"parse_ok":true,"target_rule_present":true,"confidence":"high",'
                '"reason":"original uses p after free","evidence":"printf(p) after free"}'
            ),
            (
                '{"parse_ok":true,"target_violation_removed":true,'
                '"confidence":"high","reason":"target use-after-free removed",'
                '"remaining_evidence":""}'
            ),
        ]
    )

    result = run_violation_removal_check(
        'printf("%s", p); free(p);',
        "MEM30-C",
        detector,
        method="non_target_advisory",
        audit_backend=audit,
        original_code='free(p); printf("%s", p);',
    )

    assert result.removed is True
    assert result.override_applied is True
    assert result.target_rule_detected is True
    assert result.non_target_introduced is False
    assert result.non_target_audits[0]["rule_id"] == "EXP34-C"
    assert audit.generate_calls == 3


def test_run_semantic_check() -> None:
    """Semantic gate should prompt backend and parse result."""
    backend = FakeValidationBackend(
        generated=(
            "VERDICT: PASS\n"
            "SEMANTIC_PRESERVED: YES\n"
            "TARGET_VIOLATION_REMOVED: YES\n"
            "NEW_REGRESSION: NO\n"
            "REASON: equivalent guard added"
        )
    )

    result = run_semantic_check("return *p;", "if (!p) return 0; return *p;", "EXP34-C", backend)

    assert result.verdict == SemanticVerdict.PASS
    assert result.semantic_preserved is True
    assert result.target_violation_removed is True
    assert result.new_regression is False
    assert "EXP34-C" in backend.last_prompt
    assert "return *p;" in backend.last_prompt


def test_run_semantic_check_uses_grammar_when_supported() -> None:
    """Semantic gate should constrain llama.cpp-style backends with a grammar."""
    backend = FakeGrammarValidationBackend(
        generated=(
            "VERDICT: PASS\n"
            "SEMANTIC_PRESERVED: YES\n"
            "TARGET_VIOLATION_REMOVED: YES\n"
            "NEW_REGRESSION: NO\n"
            "REASON: equivalent guard added"
        )
    )

    result = run_semantic_check("free(p);", 'printf("%s", p); free(p);', "MEM30-C", backend)

    assert result.verdict == SemanticVerdict.PASS
    assert backend.last_grammar is not None
    assert "TARGET_VIOLATION_REMOVED" in backend.last_grammar


def test_run_semantic_auto_apply_check_parses_json() -> None:
    """SPEC semantic gate should parse the JSON auto-apply contract."""
    backend = FakeValidationBackend(
        generated=(
            '{"parse_ok":true,"auto_apply_ok":true,"behavior_preserved":true,'
            '"material_behavior_delta":false,"uncertain_material_behavior":false,'
            '"fail_type":"none","confidence":"high","reason":"safe"}'
        )
    )

    result = run_semantic_auto_apply_check("old", "new", "MEM30-C", backend)

    assert result.semantic_ok is True
    assert result.auto_apply_ok is True
    assert result.fail_type == "none"
    assert "MEM30-C" in backend.last_prompt


def test_aggregate_final_status_fixed() -> None:
    """All gates passing should allow apply."""
    status = aggregate_final_status(
        compile_result=CompileCheckResult(ok=True, command=["gcc"], returncode=0),
        removal_result=ViolationRemovalResult(
            removed=True,
            target_rule_id="MEM30-C",
            remaining_violations=[],
        ),
        semantic_result=SemanticCheckResult(
            verdict=SemanticVerdict.PASS,
            semantic_preserved=True,
            target_violation_removed=True,
            new_regression=False,
        ),
    )

    assert status == FinalFixStatus.FIXED


def test_aggregate_final_status_fixed_without_stage6() -> None:
    """Standard mode can rely on Stage 7 for target-removal evidence."""
    status = aggregate_final_status(
        compile_result=CompileCheckResult(ok=True, command=["gcc"], returncode=0),
        removal_result=None,
        semantic_result=SemanticCheckResult(
            verdict=SemanticVerdict.PASS,
            semantic_preserved=True,
            target_violation_removed=True,
            new_regression=False,
        ),
    )

    assert status == FinalFixStatus.FIXED


def test_aggregate_final_status_blocks_by_gate_order() -> None:
    """Final status should prioritize earlier hard gates."""
    semantic_pass = SemanticCheckResult(
        verdict=SemanticVerdict.PASS,
        semantic_preserved=True,
        target_violation_removed=True,
        new_regression=False,
    )

    assert (
        aggregate_final_status(
            CompileCheckResult(ok=False, command=["gcc"], returncode=1),
            ViolationRemovalResult(True, "MEM30-C", []),
            semantic_pass,
        )
        == FinalFixStatus.COMPILE_FAILED
    )
    assert (
        aggregate_final_status(
            CompileCheckResult(ok=True, command=["gcc"], returncode=0),
            ViolationRemovalResult(False, "MEM30-C", []),
            semantic_pass,
        )
        == FinalFixStatus.VIOLATION_REMAINING
    )
    assert (
        aggregate_final_status(
            CompileCheckResult(ok=True, command=["gcc"], returncode=0),
            None,
            SemanticCheckResult(
                verdict=SemanticVerdict.PASS,
                semantic_preserved=True,
                target_violation_removed=False,
                new_regression=False,
            ),
        )
        == FinalFixStatus.VIOLATION_REMAINING
    )


def test_aggregate_final_status_semantic_risks() -> None:
    """Semantic fail or uncertainty should block apply."""
    compile_ok = CompileCheckResult(ok=True, command=["gcc"], returncode=0)
    removed = ViolationRemovalResult(True, "MEM30-C", [])

    assert (
        aggregate_final_status(
            compile_ok,
            removed,
            SemanticCheckResult(
                verdict=SemanticVerdict.PASS,
                semantic_preserved=True,
                target_violation_removed=True,
                new_regression=True,
            ),
        )
        == FinalFixStatus.REGRESSION_RISK
    )
    assert (
        aggregate_final_status(
            compile_ok,
            removed,
            SemanticCheckResult(
                verdict=SemanticVerdict.UNCERTAIN,
                semantic_preserved=None,
                target_violation_removed=True,
                new_regression=False,
            ),
        )
        == FinalFixStatus.SEMANTIC_RISK
    )
