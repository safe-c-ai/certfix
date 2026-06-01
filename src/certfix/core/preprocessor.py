"""C code preprocessor with comment removal and line mapping."""

import re
from dataclasses import dataclass


@dataclass
class LineMapping:
    """Mapping between original and processed line numbers."""

    original_to_processed: dict[int, int]
    processed_to_original: dict[int, int]

    def to_original(self, processed_line: int) -> int:
        """Convert processed line number to original."""
        return self.processed_to_original.get(processed_line, processed_line)

    def to_processed(self, original_line: int) -> int:
        """Convert original line number to processed."""
        return self.original_to_processed.get(original_line, original_line)


class Preprocessor:
    """Preprocessor for C code."""

    # Pattern for certfix:ignore comments
    IGNORE_PATTERN = re.compile(r"//\s*certfix:ignore\s*(\S*)")

    def __init__(self, keep_comments: bool = False) -> None:
        """Initialize preprocessor.

        Args:
            keep_comments: If True, keep comments in output.
        """
        self.keep_comments = keep_comments

    def process(self, code: str) -> tuple[str, LineMapping, set[tuple[int, str]]]:
        """Process C code.

        Args:
            code: Original C code.

        Returns:
            Tuple of (processed code, line mapping, ignored rules).
            Ignored rules is a set of (line_number, rule_id) tuples.
        """
        if self.keep_comments:
            # No processing needed
            lines = code.split("\n")
            mapping = LineMapping(
                original_to_processed={i: i for i in range(1, len(lines) + 1)},
                processed_to_original={i: i for i in range(1, len(lines) + 1)},
            )
            return code, mapping, set()

        # Extract ignore directives before removing comments
        ignored = self._extract_ignores(code)

        # Remove comments while preserving line structure
        processed, mapping = self._remove_comments(code)

        return processed, mapping, ignored

    def _extract_ignores(self, code: str) -> set[tuple[int, str]]:
        """Extract certfix:ignore directives.

        Args:
            code: C code with comments.

        Returns:
            Set of (line_number, rule_id) tuples.
        """
        ignored: set[tuple[int, str]] = set()
        lines = code.split("\n")

        for i, line in enumerate(lines, start=1):
            match = self.IGNORE_PATTERN.search(line)
            if match:
                rule_id = match.group(1) or "*"  # * means ignore all rules
                ignored.add((i, rule_id))

        return ignored

    def _remove_comments(self, code: str) -> tuple[str, LineMapping]:
        """Remove comments while preserving line numbers.

        Comments are replaced with spaces to maintain character positions.

        Args:
            code: Original C code.

        Returns:
            Tuple of (processed code, line mapping).
        """
        result = []
        lines = code.split("\n")
        in_block_comment = False

        for line in lines:
            processed_line = ""
            i = 0
            while i < len(line):
                if in_block_comment:
                    # Look for end of block comment
                    if i < len(line) - 1 and line[i : i + 2] == "*/":
                        processed_line += "  "
                        i += 2
                        in_block_comment = False
                    else:
                        processed_line += " "
                        i += 1
                elif i < len(line) - 1 and line[i : i + 2] == "/*":
                    # Start of block comment
                    processed_line += "  "
                    i += 2
                    in_block_comment = True
                elif i < len(line) - 1 and line[i : i + 2] == "//":
                    # Line comment - replace rest of line with spaces
                    processed_line += " " * (len(line) - i)
                    break
                else:
                    processed_line += line[i]
                    i += 1

            result.append(processed_line)

        # Build line mapping (1:1 since we preserve line structure)
        mapping = LineMapping(
            original_to_processed={i: i for i in range(1, len(lines) + 1)},
            processed_to_original={i: i for i in range(1, len(lines) + 1)},
        )

        return "\n".join(result), mapping
