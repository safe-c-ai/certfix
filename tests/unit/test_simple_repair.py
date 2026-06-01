"""Tests for direct simple-mode repair parsing."""

from unittest.mock import MagicMock

from certfix.core.simple_repair import (
    parse_code_only_repair,
    parse_simple_repair,
    run_simple_repair,
)


def test_parse_simple_apply_fix() -> None:
    output = """DECISION: APPLY_FIX
RULE: MEM30-C
LINE: 3
EVIDENCE: p is used after free
```c
void f(void) {}
```"""

    result = parse_simple_repair(output)

    assert result.decision == "APPLY_FIX"
    assert result.rule_id == "MEM30-C"
    assert result.line == 3
    assert result.evidence == "p is used after free"
    assert result.fixed_code == "void f(void) {}"


def test_parse_simple_apply_fix_strips_comments() -> None:
    output = """DECISION: APPLY_FIX
RULE: MEM30-C
LINE: 3
EVIDENCE: p is used after free
```c
void f(void) {
    /* violation comment from input */
    puts(p); // print before free
    free(p);
}
```"""

    result = parse_simple_repair(output)

    assert result.fixed_code == "void f(void) {\n\n    puts(p);\n    free(p);\n}"
    assert "violation comment" not in result.fixed_code
    assert "print before free" not in result.fixed_code


def test_parse_simple_apply_fix_keeps_comment_markers_inside_strings() -> None:
    output = """DECISION: APPLY_FIX
RULE: MEM30-C
LINE: 3
EVIDENCE: p is used after free
```c
void f(void) {
    puts("https://example.com/path/*not-comment*/");
    free(p);
}
```"""

    result = parse_simple_repair(output)

    assert '"https://example.com/path/*not-comment*/"' in result.fixed_code


def test_parse_simple_apply_fix_uses_final_code_fence() -> None:
    output = """The input was:
```c
void f(void) { free(p); puts(p); }
```
DECISION: APPLY_FIX
RULE: MEM30-C
LINE: 1
EVIDENCE: p is used after free
```c
void f(void) { puts(p); free(p); }
```"""

    result = parse_simple_repair(output)

    assert result.fixed_code == "void f(void) { puts(p); free(p); }"


def test_parse_simple_apply_fix_ignores_placeholder_fence() -> None:
    output = """DECISION: APPLY_FIX
RULE: MEM30-C
LINE: 1
EVIDENCE: p is used after free
```c
void f(void) { puts(p); free(p); }
```
```c
<complete fixed C source file>
```"""

    result = parse_simple_repair(output)

    assert result.fixed_code == "void f(void) { puts(p); free(p); }"


def test_run_simple_repair_no_violations_returns_none() -> None:
    backend = MagicMock()
    backend.generate.return_value = "DECISION: NO_VIOLATIONS"

    result = run_simple_repair("int main(void) { return 0; }", "clean.c", backend)

    assert result is None


def test_run_simple_repair_unresolved_returns_failed_fix() -> None:
    backend = MagicMock()
    backend.generate.return_value = """DECISION: UNRESOLVED
EVIDENCE: requires cross-file reasoning"""

    result = run_simple_repair("int f(void);", "test.c", backend)

    assert result is not None
    assert result.success is False
    assert result.violation.rule_id == "UNKNOWN"
    assert result.error_message == "requires cross-file reasoning"


def test_parse_code_only_repair_changed_code() -> None:
    result = parse_code_only_repair(
        "void f(void) { puts(p); free(p); }",
        "void f(void) { free(p); puts(p); }",
        "MEM30-C",
    )

    assert result.decision == "APPLY_FIX"
    assert result.rule_id == "MEM30-C"
    assert result.fixed_code == "void f(void) { puts(p); free(p); }"


def test_parse_code_only_repair_unchanged_code_is_no_violation() -> None:
    code = "int main(void) { return 0; }"

    result = parse_code_only_repair(code, code, "MEM30-C")

    assert result.decision == "NO_VIOLATIONS"


def test_parse_code_only_repair_comment_only_change_is_no_violation() -> None:
    code = "int main(void) { /* note */ return 0; }"

    result = parse_code_only_repair("int main(void) {  return 0; }", code, "MEM30-C")

    assert result.decision == "NO_VIOLATIONS"


def test_run_simple_repair_qwen36_code_only_profile() -> None:
    backend = MagicMock()
    backend.generate.return_value = "void f(void) { puts(p); free(p); }"

    result = run_simple_repair(
        "void f(void) { free(p); puts(p); }",
        "test.c",
        backend,
        rules=["MEM30-C"],
        prompt_profile="qwen36_27b_zs_fix_code_only_v1",
    )

    assert result is not None
    assert result.success is True
    assert result.violation.rule_id == "MEM30-C"
    assert result.fixed_code == "void f(void) { puts(p); free(p); }"
    prompt = backend.generate.call_args.args[0]
    assert "CERT-C rule MEM30-C violation" in prompt
    assert "Output only C code" in prompt
