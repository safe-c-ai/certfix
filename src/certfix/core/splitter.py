"""C source file splitter for function-level chunk detection."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Pattern to match function definition signatures.
# Captures optional qualifiers + return type + function name + opening paren.
# Does NOT match declarations (ending with ;) or preprocessor directives.
_FUNC_START_RE = re.compile(
    r"^\s*"
    r"(?:(?:static|extern|inline|const|volatile|unsigned|signed"
    r"|long|short|struct|enum|union|void|int|char|float|double"
    r"|size_t|ssize_t|uint\d+_t|int\d+_t|bool|_Bool)\s+)*"
    r"[\w][\w\s]*"  # return type
    r"[*\s]+"  # separator (space or pointer *)
    r"(\w+)"  # function name (captured)
    r"\s*\("  # opening paren
)


@dataclass
class Chunk:
    """A chunk of C source code extracted from a file."""

    code: str
    start_line: int  # 1-based start line in the source
    end_line: int  # 1-based end line (inclusive)
    is_function: bool
    name: str = ""  # function name, or "" for non-function


def split_functions(code: str) -> list[Chunk]:
    """Split C source code into function-level chunks.

    Expects preprocessed code (comments already removed).
    Returns function chunks and non-function chunks (preamble, globals).
    Returns empty list if parsing fails (unbalanced braces).

    Args:
        code: C source code (comments should already be removed).

    Returns:
        List of Chunk objects. Empty list on parse failure.
    """
    if not code or not code.strip():
        return []

    lines = code.split("\n")

    try:
        boundaries = _find_function_boundaries(lines)
    except _ParseError:
        logger.warning("Failed to parse function boundaries, falling back")
        return []

    if not boundaries:
        # No functions found — return whole file as non-function chunk
        return [
            Chunk(
                code=code,
                start_line=1,
                end_line=len(lines),
                is_function=False,
            )
        ]

    chunks: list[Chunk] = []
    prev_end = 0  # 0-based line index of previous function end

    for func_name, func_start, func_end in boundaries:
        # Non-function code before this function
        if func_start > prev_end:
            preamble_lines = lines[prev_end:func_start]
            preamble_text = "\n".join(preamble_lines)
            if preamble_text.strip():
                chunks.append(
                    Chunk(
                        code=preamble_text,
                        start_line=prev_end + 1,
                        end_line=func_start,
                        is_function=False,
                    )
                )

        # Function chunk
        func_lines = lines[func_start : func_end + 1]
        chunks.append(
            Chunk(
                code="\n".join(func_lines),
                start_line=func_start + 1,  # 1-based
                end_line=func_end + 1,  # 1-based
                is_function=True,
                name=func_name,
            )
        )
        prev_end = func_end + 1

    # Trailing non-function code after last function
    if prev_end < len(lines):
        trailing_lines = lines[prev_end:]
        trailing_text = "\n".join(trailing_lines)
        if trailing_text.strip():
            chunks.append(
                Chunk(
                    code=trailing_text,
                    start_line=prev_end + 1,
                    end_line=len(lines),
                    is_function=False,
                )
            )

    return chunks


class _ParseError(Exception):
    pass


def _find_function_boundaries(
    lines: list[str],
) -> list[tuple[str, int, int]]:
    """Find function definition boundaries.

    Returns list of (func_name, start_line_idx, end_line_idx)
    where indices are 0-based.

    Raises _ParseError on unbalanced braces.
    """
    functions: list[tuple[str, int, int]] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Skip preprocessor directives
        if line.lstrip().startswith("#"):
            i += 1
            continue

        # Try to match a function signature on this line
        match = _FUNC_START_RE.match(line)

        # If no match, try joining with next line(s) for multiline signatures
        # Only attempt if current line has content (type/qualifier)
        if not match and i + 1 < n and line.strip():
            joined = line + " " + lines[i + 1]
            match = _FUNC_START_RE.match(joined)
            if not match and i + 2 < n:
                joined = joined + " " + lines[i + 2]
                match = _FUNC_START_RE.match(joined)

        if match:
            func_name = match.group(1)
            # Find the opening brace (may be on this line or subsequent)
            brace_line = _find_opening_brace(lines, i)
            if brace_line is not None:
                # Found a function definition
                end_line = _find_closing_brace(lines, brace_line)
                if end_line is None:
                    raise _ParseError("Unbalanced braces")
                functions.append((func_name, i, end_line))
                i = end_line + 1
                continue

        i += 1

    return functions


def _find_opening_brace(lines: list[str], start: int) -> int | None:
    """Find the line with the opening { for a function starting at 'start'.

    Searches up to 5 lines ahead for the opening brace.
    Returns the 0-based line index, or None if not found.
    """
    max_lookahead = min(start + 5, len(lines))
    for i in range(start, max_lookahead):
        line = lines[i]
        # Check for opening brace, ignoring braces in strings
        if _contains_opening_brace(line):
            return i
        # If we hit a semicolon first, it's a declaration, not definition
        if ";" in line and "{" not in line:
            return None
    return None


def _find_closing_brace(lines: list[str], brace_line: int) -> int | None:
    """Find the closing } that matches the opening { on brace_line.

    Returns the 0-based line index, or None if unbalanced.
    """
    depth = 0
    in_string = False
    escape = False

    for i in range(brace_line, len(lines)):
        for ch in lines[i]:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not in_string:
                in_string = True
                continue
            if ch == '"' and in_string:
                in_string = False
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i

    return None


def _contains_opening_brace(line: str) -> bool:
    """Check if a line contains { outside of string literals."""
    in_string = False
    escape = False
    for ch in line:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string and ch == "{":
            return True
    return False
