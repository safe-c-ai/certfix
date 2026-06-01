"""CERT-C violation detector."""

from __future__ import annotations

import logging
from pathlib import Path

from certfix.core.include_resolver import IncludeResolver
from certfix.core.preprocessor import Preprocessor
from certfix.core.splitter import Chunk, split_functions
from certfix.inference.base import InferenceBackend
from certfix.models import CheckResult, Violation

logger = logging.getLogger(__name__)


class Detector:
    """Detector for CERT-C violations."""

    def __init__(
        self,
        backend: InferenceBackend,
        preprocessor: Preprocessor | None = None,
        include_resolver: IncludeResolver | None = None,
    ) -> None:
        """Initialize detector.

        Args:
            backend: Inference backend for LLM.
            preprocessor: Code preprocessor. If None, creates default.
            include_resolver: Header include resolver. If None, no header context.
        """
        self.backend = backend
        self.preprocessor = preprocessor or Preprocessor()
        self.include_resolver = include_resolver

    def check_file(self, path: Path, rules: list[str] | None = None) -> list[Violation]:
        """Check a single file for violations.

        Splits C files into function-level chunks for detection.
        Non-function code preceding each function is prepended as context.
        Line numbers are remapped back to the original file.

        Args:
            path: Path to C source file.
            rules: List of rule IDs to check. If None, check all.

        Returns:
            List of detected violations.
        """
        code = path.read_text(encoding="utf-8")
        processed, mapping, ignored = self.preprocessor.process(code)

        # Split into function-level chunks
        chunks = split_functions(processed)
        if not chunks:
            # Fallback: treat whole file as one chunk
            lines = processed.split("\n")
            chunks = [
                Chunk(
                    code=processed,
                    start_line=1,
                    end_line=len(lines),
                    is_function=False,
                )
            ]

        # Extract header context (types, macros from #include "..." headers)
        header_context = ""
        if self.include_resolver:
            header_context = self.include_resolver.extract_header_context(path, code)

        line_aware_detection = _is_line_aware_backend(self.backend)

        # Detect violations in each chunk
        all_violations: list[Violation] = []
        for i, chunk in enumerate(chunks):
            if _is_preprocessor_only_chunk(chunk):
                continue

            # Prepend header + preceding non-function code as context
            file_context = _build_preceding_context(chunks, i)
            parts = [p for p in [header_context, file_context] if p]
            context = "\n".join(parts)

            if chunk.is_function and context:
                code_with_context = context + "\n\n" + chunk.code
                context_line_count = context.count("\n") + 2
            else:
                code_with_context = chunk.code
                context_line_count = 0

            try:
                chunk_violations = self.backend.detect(code_with_context, rules)
            except Exception:
                logger.warning(
                    "Detection failed for chunk %s in %s",
                    chunk.name or "non-function",
                    path,
                    exc_info=True,
                )
                continue

            for v in chunk_violations:
                # Remap line number from combined-code-relative to file-level
                if chunk.is_function and not line_aware_detection:
                    remapped = chunk.start_line
                else:
                    remapped = chunk.start_line + (v.line - context_line_count - 1)

                # Discard violations from the context portion or invalid lines
                if remapped < chunk.start_line:
                    continue
                if remapped < 1:
                    continue

                v.line = remapped
                all_violations.append(v)

        # Deduplicate by (rule_id, line)
        violations = _deduplicate(all_violations)

        # Filter ignored violations and map line numbers to original
        result = []
        for v in violations:
            original_line = mapping.to_original(v.line)

            # Check if this violation is ignored
            is_ignored = False
            for ignore_line, ignore_rule in ignored:
                if (ignore_line == original_line or ignore_line == original_line - 1) and (
                    ignore_rule == "*" or ignore_rule == v.rule_id
                ):
                    is_ignored = True
                    break

            if not is_ignored:
                v.line = original_line
                v.file_path = str(path)
                result.append(v)

        return result

    def check_directory(
        self,
        path: Path,
        rules: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> CheckResult:
        """Check all C files in a directory.

        Args:
            path: Path to directory.
            rules: List of rule IDs to check.
            exclude: Patterns to exclude.

        Returns:
            Check result with all violations.
        """
        exclude = exclude or []
        violations: list[Violation] = []
        files_checked = 0

        for c_file in sorted(path.rglob("*.[ch]")):
            # Check exclusions
            if any(pattern in str(c_file) for pattern in exclude):
                continue

            files_checked += 1
            violations.extend(self.check_file(c_file, rules))

        return CheckResult(files_checked=files_checked, violations=violations)


def _build_preceding_context(chunks: list[Chunk], current_index: int) -> str:
    """Build context from non-function chunks that precede the current chunk."""
    parts = []
    for chunk in chunks[:current_index]:
        stripped = chunk.code.strip()
        if not chunk.is_function and stripped:
            parts.append(stripped)
    return "\n".join(parts)


def _deduplicate(violations: list[Violation]) -> list[Violation]:
    """Remove duplicate violations by (rule_id, line)."""
    seen: set[tuple[str, int]] = set()
    result: list[Violation] = []
    for v in violations:
        key = (v.rule_id, v.line)
        if key not in seen:
            seen.add(key)
            result.append(v)
    return result


def _is_line_aware_backend(backend: InferenceBackend) -> bool:
    """Return whether a backend reports line numbers relative to its input."""
    value = getattr(backend, "line_aware_detection", True)
    return value if isinstance(value, bool) else True


def _is_preprocessor_only_chunk(chunk: Chunk) -> bool:
    """Return whether a non-function chunk contains only preprocessor lines."""
    if chunk.is_function:
        return False

    nonblank_lines = [line.strip() for line in chunk.code.splitlines() if line.strip()]
    return bool(nonblank_lines) and all(line.startswith("#") for line in nonblank_lines)
