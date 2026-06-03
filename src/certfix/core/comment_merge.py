"""Conservative comment reattachment for validated fixed-code candidates."""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from certfix.inference.base import InferenceBackend


class CommentMergeStatus(Enum):
    """Outcome for a comment-merge attempt."""

    MERGED = "merged"
    SKIPPED_NO_COMMENTS = "skipped_no_comments"
    SKIPPED_NO_STABLE_ANCHORS = "skipped_no_stable_anchors"


@dataclass(frozen=True)
class CommentMergeDecision:
    """One conservative keep/drop decision made by the merge pass."""

    kind: str
    original_line: int
    status: str
    reason: str
    fixed_line: int | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "kind": self.kind,
            "original_line": self.original_line,
            "status": self.status,
            "reason": self.reason,
        }
        if self.fixed_line is not None:
            data["fixed_line"] = self.fixed_line
        return data


@dataclass(frozen=True)
class CommentMergeResult:
    """Result of conservatively reattaching comments."""

    status: CommentMergeStatus
    merged_code: str
    restored_comments: int
    skipped_comments: int
    decisions: list[CommentMergeDecision] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status == CommentMergeStatus.MERGED

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "success": self.success,
            "restored_comments": self.restored_comments,
            "skipped_comments": self.skipped_comments,
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


@dataclass(frozen=True)
class CommentMergeAuditResult:
    """LLM audit result for a comment-merged artifact."""

    parse_ok: bool
    audit_ok: bool
    comments_consistent: bool | None
    disabled_code_restored: bool | None
    misleading_comments: list[str]
    confidence: str
    reason: str
    raw_output: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "parse_ok": self.parse_ok,
            "audit_ok": self.audit_ok,
            "comments_consistent": self.comments_consistent,
            "disabled_code_restored": self.disabled_code_restored,
            "misleading_comments": self.misleading_comments,
            "confidence": self.confidence,
            "reason": self.reason,
            "raw_output": self.raw_output,
        }


@dataclass(frozen=True)
class _Comment:
    kind: str
    text: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int


def merge_comments(original_code: str, fixed_code: str) -> CommentMergeResult:
    """Return fixed code with safely reattached comments from original code.

    The merge uses the comment-stripped original as the base and only reattaches
    comments to unchanged code lines that can be mapped to the fixed candidate.
    Ambiguous comments are skipped; this function must not change executable
    code beyond adding comments.
    """

    stripped_original, comments = _strip_comments_with_spans(original_code)
    if not comments:
        return CommentMergeResult(
            status=CommentMergeStatus.SKIPPED_NO_COMMENTS,
            merged_code=fixed_code,
            restored_comments=0,
            skipped_comments=0,
        )

    original_lines = stripped_original.splitlines()
    fixed_lines = fixed_code.splitlines()
    fixed_had_trailing_newline = fixed_code.endswith("\n")
    line_map = _equal_line_map(original_lines, fixed_lines)

    insertions: dict[int, list[str]] = {}
    trailing: dict[int, list[str]] = {}
    decisions: list[CommentMergeDecision] = []
    restored = 0
    skipped = 0

    for comment in comments:
        if _looks_like_commented_out_code(comment.text):
            skipped += 1
            decisions.append(
                CommentMergeDecision(
                    kind=comment.kind,
                    original_line=comment.start_line + 1,
                    status="skipped",
                    reason="comment appears to contain disabled code",
                )
            )
            continue

        if _is_trailing_comment(comment, original_lines):
            mapped = line_map.get(comment.start_line)
            if mapped is None:
                skipped += 1
                decisions.append(
                    CommentMergeDecision(
                        kind=comment.kind,
                        original_line=comment.start_line + 1,
                        status="skipped",
                        reason="comment is attached to a changed line",
                    )
                )
                continue
            trailing.setdefault(mapped, []).append(_one_line_comment_text(comment.text))
            restored += 1
            decisions.append(
                CommentMergeDecision(
                    kind=comment.kind,
                    original_line=comment.start_line + 1,
                    fixed_line=mapped + 1,
                    status="restored",
                    reason="trailing comment attached to unchanged line",
                )
            )
            continue

        if _is_standalone_comment(comment, original_lines):
            anchor = _next_nonblank_line(original_lines, comment.end_line + 1)
            mapped = (
                line_map.get(anchor)
                if anchor is not None and _is_safe_standalone_anchor(original_lines[anchor])
                else None
            )
            if mapped is None:
                skipped += 1
                decisions.append(
                    CommentMergeDecision(
                        kind=comment.kind,
                        original_line=comment.start_line + 1,
                        status="skipped",
                        reason="standalone comment has no stable following code anchor",
                    )
                )
                continue
            insertions.setdefault(mapped, []).extend(
                _comment_lines(comment.text, _line_indent(fixed_lines[mapped]))
            )
            restored += 1
            decisions.append(
                CommentMergeDecision(
                    kind=comment.kind,
                    original_line=comment.start_line + 1,
                    fixed_line=mapped + 1,
                    status="restored",
                    reason="standalone comment inserted before unchanged code anchor",
                )
            )
            continue

        skipped += 1
        decisions.append(
            CommentMergeDecision(
                kind=comment.kind,
                original_line=comment.start_line + 1,
                status="skipped",
                reason="comment placement is not safe to reattach",
            )
        )

    if restored == 0:
        return CommentMergeResult(
            status=CommentMergeStatus.SKIPPED_NO_STABLE_ANCHORS,
            merged_code=fixed_code,
            restored_comments=0,
            skipped_comments=skipped,
            decisions=decisions,
        )

    merged_lines: list[str] = []
    for index, line in enumerate(fixed_lines):
        merged_lines.extend(insertions.get(index, []))
        if index in trailing:
            suffix = " ".join(text.strip() for text in trailing[index])
            merged_lines.append(f"{line.rstrip()} {suffix}")
        else:
            merged_lines.append(line)

    merged_code = "\n".join(merged_lines)
    if fixed_had_trailing_newline:
        merged_code += "\n"
    return CommentMergeResult(
        status=CommentMergeStatus.MERGED,
        merged_code=merged_code,
        restored_comments=restored,
        skipped_comments=skipped,
        decisions=decisions,
    )


def comment_merged_diff(original_code: str, merged_code: str, file_path: str) -> str:
    """Return a unified diff from original code to comment-merged fixed code."""

    diff = difflib.unified_diff(
        original_code.splitlines(keepends=True),
        merged_code.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)


def audit_comment_merge(
    *,
    original_code: str,
    fixed_code: str,
    merged_code: str,
    backend: InferenceBackend,
    max_tokens: int = 1024,
) -> CommentMergeAuditResult:
    """Ask an LLM to audit whether restored comments remain consistent."""

    prompt = COMMENT_MERGE_AUDIT_PROMPT.format(
        original_code=original_code,
        fixed_code=fixed_code,
        merged_code=merged_code,
    )
    output = backend.generate(prompt, max_tokens=max_tokens, temperature=0.0)
    return parse_comment_merge_audit(output)


def parse_comment_merge_audit(output: str) -> CommentMergeAuditResult:
    """Parse the structured comment-merge audit JSON."""

    obj = _extract_json_object(output)
    if obj is None:
        return CommentMergeAuditResult(
            parse_ok=False,
            audit_ok=False,
            comments_consistent=None,
            disabled_code_restored=None,
            misleading_comments=[],
            confidence="low",
            reason="comment-merge audit output was not valid JSON",
            raw_output=output,
        )

    required = {
        "audit_ok",
        "comments_consistent",
        "disabled_code_restored",
        "misleading_comments",
        "confidence",
        "reason",
    }
    missing = sorted(required - set(obj))
    if missing:
        return CommentMergeAuditResult(
            parse_ok=False,
            audit_ok=False,
            comments_consistent=None,
            disabled_code_restored=None,
            misleading_comments=[],
            confidence="low",
            reason=f"comment-merge audit JSON missing fields: {', '.join(missing)}",
            raw_output=output,
        )

    comments_consistent = _json_bool(obj.get("comments_consistent"))
    disabled_code_restored = _json_bool(obj.get("disabled_code_restored"))
    confidence = str(obj.get("confidence") or "low").strip().lower()
    confidence_ok = confidence in {"high", "medium"}
    misleading = obj.get("misleading_comments")
    if isinstance(misleading, list):
        misleading_comments_ok = True
        misleading_list: list[Any] = misleading
    else:
        misleading_comments_ok = False
        misleading_list = []
    misleading_comments = (
        [str(item) for item in misleading_list if item is not None]
        if misleading_comments_ok
        else []
    )
    audit_ok_field = _json_bool(obj.get("audit_ok"))
    reason = str(obj.get("reason") or "")
    if not misleading_comments_ok and not reason:
        reason = "comment-merge audit JSON field misleading_comments was not a list"
    audit_ok = (
        audit_ok_field is True
        and comments_consistent is True
        and disabled_code_restored is False
        and confidence_ok
        and misleading_comments_ok
        and not misleading_comments
    )
    return CommentMergeAuditResult(
        parse_ok=True,
        audit_ok=audit_ok,
        comments_consistent=comments_consistent,
        disabled_code_restored=disabled_code_restored,
        misleading_comments=misleading_comments,
        confidence=confidence,
        reason=reason,
        raw_output=output,
    )


COMMENT_MERGE_AUDIT_PROMPT = """/no_think
You are auditing comments that were reattached after a C code fix.
Return only one JSON object. Do not include markdown, prose, or analysis.

The validated fixed code below is authoritative. Review only whether comments in
the comment-merged code remain accurate for that fixed code.

Original code with comments:
```c
{original_code}
```

Validated fixed code without comments:
```c
{fixed_code}
```

Comment-merged fixed code:
```c
{merged_code}
```

Use this exact JSON shape:
{{
  "audit_ok": true,
  "comments_consistent": true,
  "disabled_code_restored": false,
  "misleading_comments": [],
  "confidence": "high",
  "reason": "short reason"
}}

Rules:
- Set "audit_ok" to false if any restored comment contradicts the fixed code.
- Set "audit_ok" to false if a comment describes old control flow, old resource
  lifetime, old bounds, old ownership, or an old API contract.
- Set "disabled_code_restored" to true if commented-out code appears to have
  been restored as a comment.
- Set "confidence" to "low" if the comment/code relationship is unclear.
- Keep "misleading_comments" as an array of short strings.
"""


def _strip_comments_with_spans(code: str) -> tuple[str, list[_Comment]]:
    result: list[str] = []
    comments: list[_Comment] = []
    i = 0
    line = 0
    col = 0
    state = "normal"
    comment_start = 0
    comment_line = 0
    comment_col = 0

    while i < len(code):
        ch = code[i]
        nxt = code[i + 1] if i + 1 < len(code) else ""

        if state == "normal":
            if ch == "/" and nxt == "/":
                comment_start = i
                comment_line = line
                comment_col = col
                state = "line_comment"
                i += 2
                col += 2
                continue
            if ch == "/" and nxt == "*":
                comment_start = i
                comment_line = line
                comment_col = col
                state = "block_comment"
                i += 2
                col += 2
                continue
            if ch == '"':
                state = "string"
            elif ch == "'":
                state = "char"
            result.append(ch)
            i, line, col = _advance_position(i, line, col, ch)
            continue

        if state == "string":
            result.append(ch)
            if ch == "\\" and nxt:
                result.append(nxt)
                i, line, col = _advance_position(i, line, col, ch)
                i, line, col = _advance_position(i, line, col, nxt)
                continue
            if ch == '"':
                state = "normal"
            i, line, col = _advance_position(i, line, col, ch)
            continue

        if state == "char":
            result.append(ch)
            if ch == "\\" and nxt:
                result.append(nxt)
                i, line, col = _advance_position(i, line, col, ch)
                i, line, col = _advance_position(i, line, col, nxt)
                continue
            if ch == "'":
                state = "normal"
            i, line, col = _advance_position(i, line, col, ch)
            continue

        if state == "line_comment":
            if ch == "\n":
                comments.append(
                    _Comment(
                        kind="line",
                        text=code[comment_start:i],
                        start_line=comment_line,
                        start_col=comment_col,
                        end_line=line,
                        end_col=col,
                    )
                )
                result.append(ch)
                state = "normal"
                i, line, col = _advance_position(i, line, col, ch)
                continue
            i, line, col = _advance_position(i, line, col, ch)
            continue

        if state == "block_comment":
            if ch == "\n":
                result.append(ch)
                i, line, col = _advance_position(i, line, col, ch)
                continue
            if ch == "*" and nxt == "/":
                end_i = i + 2
                comments.append(
                    _Comment(
                        kind="block",
                        text=code[comment_start:end_i],
                        start_line=comment_line,
                        start_col=comment_col,
                        end_line=line,
                        end_col=col + 2,
                    )
                )
                state = "normal"
                i += 2
                col += 2
                continue
            i, line, col = _advance_position(i, line, col, ch)
            continue

    if state == "line_comment":
        comments.append(
            _Comment(
                kind="line",
                text=code[comment_start:],
                start_line=comment_line,
                start_col=comment_col,
                end_line=line,
                end_col=col,
            )
        )
    elif state == "block_comment":
        comments.append(
            _Comment(
                kind="block",
                text=code[comment_start:],
                start_line=comment_line,
                start_col=comment_col,
                end_line=line,
                end_col=col,
            )
        )

    return "".join(result), comments


def _advance_position(i: int, line: int, col: int, ch: str) -> tuple[int, int, int]:
    if ch == "\n":
        return i + 1, line + 1, 0
    return i + 1, line, col + 1


def _equal_line_map(original_lines: list[str], fixed_lines: list[str]) -> dict[int, int]:
    original_norm = [_normalize_code_line(line) for line in original_lines]
    fixed_norm = [_normalize_code_line(line) for line in fixed_lines]
    original_counts = Counter(line for line in original_norm if line)
    fixed_counts = Counter(line for line in fixed_norm if line)
    matcher = difflib.SequenceMatcher(None, original_norm, fixed_norm, autojunk=False)
    line_map: dict[int, int] = {}
    for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset, original_index in enumerate(range(i1, i2)):
            normalized = original_norm[original_index]
            if normalized and original_counts[normalized] == 1 and fixed_counts[normalized] == 1:
                line_map[original_index] = j1 + offset
    return line_map


def _normalize_code_line(line: str) -> str:
    return line.strip()


def _is_trailing_comment(comment: _Comment, original_lines: list[str]) -> bool:
    if comment.start_line >= len(original_lines):
        return False
    if comment.start_line != comment.end_line:
        return False
    before = original_lines[comment.start_line][: comment.start_col]
    after = original_lines[comment.start_line][comment.start_col :]
    return bool(before.strip()) and not after.strip()


def _is_standalone_comment(comment: _Comment, original_lines: list[str]) -> bool:
    if comment.start_line >= len(original_lines):
        return True
    first_line_before = original_lines[comment.start_line][: comment.start_col]
    last_line_after = (
        original_lines[comment.end_line][comment.end_col :]
        if comment.end_line < len(original_lines)
        else ""
    )
    covered = original_lines[comment.start_line : comment.end_line + 1]
    return not first_line_before.strip() and not last_line_after.strip() and all(
        not line.strip() for line in covered
    )


def _next_nonblank_line(lines: list[str], start: int) -> int | None:
    for index in range(start, len(lines)):
        if _normalize_code_line(lines[index]):
            return index
    return None


def _is_safe_standalone_anchor(line: str) -> bool:
    stripped = _normalize_code_line(line)
    if not stripped:
        return False
    if stripped in {"}", "{", "};", "else", "do"}:
        return False
    if stripped.startswith("}"):
        return False
    if re.fullmatch(r"[{};]+", stripped):
        return False
    return not stripped.startswith("#")


def _looks_like_commented_out_code(comment: str) -> bool:
    text = _comment_payload(comment)
    if re.search(r"\b[A-Za-z_]\w*\s*\([^)]*\)\s*(?://.*)?$", text, re.MULTILINE):
        return True
    if re.search(
        r"\b[A-Za-z_]\w*(?:\s*(?:\[[^\]]+\]|->\w+|\.\w+))*\s*"
        r"(?:=|\+=|-=|\*=|/=|%=|<<=|>>=|&=|\|=|\^=)",
        text,
    ):
        return True
    if re.search(r"(?:^|\s)(?:\+\+|--)\s*[A-Za-z_]\w*", text):
        return True
    if re.search(r"\b[A-Za-z_]\w*\s*(?:\+\+|--)", text):
        return True
    return bool(
        re.search(r"[;{}]", text)
        or re.search(r"^\s*#", text, re.MULTILINE)
        or re.search(r"\b(?:if|for|while|switch)\s*\(", text)
        or re.search(r"\b(?:return|goto|break|continue)\b", text)
    )


def _comment_payload(comment: str) -> str:
    text = comment.strip()
    if text.startswith("//"):
        return "\n".join(line.removeprefix("//").strip() for line in text.splitlines())
    if text.startswith("/*"):
        text = text[2:]
    if text.endswith("*/"):
        text = text[:-2]
    return "\n".join(line.strip().lstrip("*").strip() for line in text.splitlines())


def _one_line_comment_text(comment: str) -> str:
    return " ".join(line.strip() for line in comment.splitlines())


def _comment_lines(comment: str, indent: str = "") -> list[str]:
    lines = comment.splitlines() or [comment]
    if not lines:
        return []
    return [f"{indent}{lines[0]}", *lines[1:]]


def _line_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _json_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes"}:
            return True
        if normalized in {"false", "no"}:
            return False
    return None
