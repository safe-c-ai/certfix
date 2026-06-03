"""Tests for conservative comment reattachment."""

from unittest.mock import MagicMock

from certfix.core.comment_merge import (
    CommentMergeStatus,
    audit_comment_merge,
    merge_comments,
    parse_comment_merge_audit,
)


def test_merge_comments_restores_standalone_and_unchanged_trailing_comments() -> None:
    original = """/* public API entry point */
int f(int x) {
    int y = x + 1; // preserved invariant
    return y;
}
"""
    fixed = """int f(int x) {
    int y = x + 1;
    return y + 1;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.MERGED
    assert "/* public API entry point */" in result.merged_code
    assert "int y = x + 1; // preserved invariant" in result.merged_code
    assert "return y + 1;" in result.merged_code
    assert result.restored_comments == 2


def test_merge_comments_skips_trailing_comment_on_changed_line() -> None:
    original = """int f(void) {
    return 0; // old boundary
}
"""
    fixed = """int f(void) {
    return 1;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.SKIPPED_NO_STABLE_ANCHORS
    assert "old boundary" not in result.merged_code
    assert result.skipped_comments == 1


def test_merge_comments_skips_commented_out_code() -> None:
    original = """int f(void) {
    // return unsafe();
    return 0;
}
"""
    fixed = """int f(void) {
    return 0;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.SKIPPED_NO_STABLE_ANCHORS
    assert "return unsafe" not in result.merged_code
    assert result.skipped_comments == 1


def test_merge_comments_skips_bare_call_commented_out_code() -> None:
    original = """int f(void) {
    // free(p)
    return 0;
}
"""
    fixed = """int f(void) {
    return 0;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.SKIPPED_NO_STABLE_ANCHORS
    assert "free(p)" not in result.merged_code


def test_merge_comments_keeps_normal_prose_with_for_keyword() -> None:
    original = """int f(void) {
    // Check for overflow before returning.
    int x = 0;
    return x;
}
"""
    fixed = """int f(void) {
    int x = 0;
    return x + 1;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.MERGED
    assert "Check for overflow before returning." in result.merged_code


def test_merge_comments_skips_trailing_comment_when_string_literal_spacing_changes() -> None:
    original = """int f(void) {
    printf("a b"); // visible text
    return 0;
}
"""
    fixed = """int f(void) {
    printf("a    b");
    return 0;
}
"""

    result = merge_comments(original, fixed)

    assert "visible text" not in result.merged_code
    assert result.skipped_comments == 1


def test_merge_comments_does_not_anchor_standalone_comment_to_closing_brace() -> None:
    original = """int f(void) {
    int x = 0;
    // cleanup is complete
}
"""
    fixed = """int f(void) {
    int x = 1;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.SKIPPED_NO_STABLE_ANCHORS
    assert "cleanup is complete" not in result.merged_code


def test_merge_comments_does_not_anchor_to_else_boundary_line() -> None:
    original = """int f(int x) {
    if (x) {
        x += 1;
    // else note
    } else {
        x--;
    }
    return x;
}
"""
    fixed = """int f(int x) {
    if (x) {
        x += 2;
    } else {
        x--;
    }
    return x;
}
"""

    result = merge_comments(original, fixed)

    assert "else note" not in result.merged_code


def test_merge_comments_does_not_anchor_to_do_while_boundary_line() -> None:
    original = """int f(int x) {
    do {
        x++;
    // loop note
    } while (x < 10);
    return x;
}
"""
    fixed = """int f(int x) {
    do {
        x += 2;
    } while (x < 10);
    return x;
}
"""

    result = merge_comments(original, fixed)

    assert "loop note" not in result.merged_code


def test_merge_comments_preserves_standalone_comment_indentation() -> None:
    original = """int f(void) {
    // keep this note
    int x = 0;
    return x;
}
"""
    fixed = """int f(void) {
    int x = 0;
    return x + 1;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.MERGED
    assert "    // keep this note\n    int x = 0;" in result.merged_code


def test_merge_comments_skips_duplicate_code_line_anchor() -> None:
    original = """int f(int n) {
    if (n > 0) {
        return 0;
    }
    // ambiguous duplicate return
    return 0;
}
"""
    fixed = """int f(int n) {
    if (n > 0) {
        return 1;
    }
    return 0;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.SKIPPED_NO_STABLE_ANCHORS
    assert "ambiguous duplicate return" not in result.merged_code


def test_merge_comments_skips_more_commented_out_code_forms() -> None:
    original = """int f(int i) {
    // arr[i] = 0
    // ++i
    // cleanup(i) // old call
    return i;
}
"""
    fixed = """int f(int i) {
    return i;
}
"""

    result = merge_comments(original, fixed)

    assert "arr[i]" not in result.merged_code
    assert "++i" not in result.merged_code
    assert "cleanup" not in result.merged_code


def test_merge_comments_preserves_comment_markers_inside_strings() -> None:
    original = """int f(void) {
    puts("https://example.com/*not-comment*/"); // URL stays
    return 0;
}
"""
    fixed = """int f(void) {
    puts("https://example.com/*not-comment*/");
    return 1;
}
"""

    result = merge_comments(original, fixed)

    assert result.status == CommentMergeStatus.MERGED
    assert 'puts("https://example.com/*not-comment*/"); // URL stays' in result.merged_code
    assert "return 1;" in result.merged_code


def test_parse_comment_merge_audit_accepts_high_confidence_clean_result() -> None:
    result = parse_comment_merge_audit(
        """
{
  "audit_ok": true,
  "comments_consistent": true,
  "disabled_code_restored": false,
  "misleading_comments": [],
  "confidence": "high",
  "reason": "comments match the fixed code"
}
"""
    )

    assert result.parse_ok is True
    assert result.audit_ok is True
    assert result.comments_consistent is True
    assert result.disabled_code_restored is False


def test_parse_comment_merge_audit_blocks_misleading_comment() -> None:
    result = parse_comment_merge_audit(
        """
{
  "audit_ok": true,
  "comments_consistent": false,
  "disabled_code_restored": false,
  "misleading_comments": ["comment says the old free-before-use order remains"],
  "confidence": "high",
  "reason": "one comment is stale"
}
"""
    )

    assert result.parse_ok is True
    assert result.audit_ok is False
    assert result.misleading_comments == ["comment says the old free-before-use order remains"]


def test_parse_comment_merge_audit_blocks_string_false_audit_ok() -> None:
    result = parse_comment_merge_audit(
        """
{
  "audit_ok": "false",
  "comments_consistent": true,
  "disabled_code_restored": false,
  "misleading_comments": [],
  "confidence": "high",
  "reason": "model used a string"
}
"""
    )

    assert result.parse_ok is True
    assert result.audit_ok is False


def test_parse_comment_merge_audit_blocks_non_list_misleading_comments() -> None:
    result = parse_comment_merge_audit(
        """
{
  "audit_ok": true,
  "comments_consistent": true,
  "disabled_code_restored": false,
  "misleading_comments": "none",
  "confidence": "high",
  "reason": ""
}
"""
    )

    assert result.parse_ok is True
    assert result.audit_ok is False
    assert "misleading_comments" in result.reason


def test_parse_comment_merge_audit_blocks_unknown_confidence() -> None:
    result = parse_comment_merge_audit(
        """
{
  "audit_ok": true,
  "comments_consistent": true,
  "disabled_code_restored": false,
  "misleading_comments": [],
  "confidence": "banana",
  "reason": "unknown confidence"
}
"""
    )

    assert result.parse_ok is True
    assert result.audit_ok is False


def test_audit_comment_merge_calls_backend_with_comment_merged_code() -> None:
    backend = MagicMock()
    backend.generate.return_value = """
{
  "audit_ok": true,
  "comments_consistent": true,
  "disabled_code_restored": false,
  "misleading_comments": [],
  "confidence": "high",
  "reason": "ok"
}
"""

    result = audit_comment_merge(
        original_code="int f(void) { return 0; }",
        fixed_code="int f(void) { return 1; }",
        merged_code="/* note */\nint f(void) { return 1; }",
        backend=backend,
        max_tokens=123,
    )

    assert result.audit_ok is True
    prompt = backend.generate.call_args.args[0]
    assert "Comment-merged fixed code" in prompt
    assert "/* note */" in prompt
    assert backend.generate.call_args.kwargs["max_tokens"] == 123
    assert backend.generate.call_args.kwargs["temperature"] == 0.0
