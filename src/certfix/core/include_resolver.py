"""Resolve #include directives and extract non-function context from headers."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from certfix.core.preprocessor import Preprocessor
from certfix.core.splitter import split_functions

logger = logging.getLogger(__name__)

_INCLUDE_RE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.MULTILINE)


class IncludeResolver:
    """Resolve local #include directives and extract header context."""

    def __init__(
        self,
        include_dirs: list[str] | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._include_dirs = [Path(d) for d in (include_dirs or [])]
        self._project_root = (project_root or Path.cwd()).resolve()
        self._cache: dict[Path, str] = {}
        self._preprocessor = Preprocessor()

    def extract_header_context(
        self,
        source_path: Path,
        source_code: str,
    ) -> str:
        """Extract non-function code from headers included by source file.

        Only processes `#include "..."` (not `<...>`).
        Resolves headers from source directory and configured include_dirs.
        Results are cached per resolved path.

        Args:
            source_path: Path to the .c source file.
            source_code: Raw source code (before preprocessing).

        Returns:
            Combined non-function code from resolved headers.
        """
        header_names = _INCLUDE_RE.findall(source_code)
        if not header_names:
            return ""

        source_dir = source_path.resolve().parent
        parts: list[str] = []
        seen: set[Path] = set()

        for name in header_names:
            resolved = self._resolve_path(source_dir, name)
            if resolved is None or resolved in seen:
                continue
            seen.add(resolved)

            context = self._get_header_context(resolved)
            if context:
                parts.append(context)

        return "\n".join(parts)

    def _resolve_path(self, source_dir: Path, header_name: str) -> Path | None:
        """Resolve header path from source directory and include_dirs."""
        candidates = [source_dir / header_name] + [d / header_name for d in self._include_dirs]
        for candidate in candidates:
            resolved = candidate.resolve()
            if not self._is_safe_path(resolved):
                logger.warning("Path traversal blocked: %s", candidate)
                continue
            if resolved.is_file():
                return resolved

        logger.debug("Header not found: %s", header_name)
        return None

    def _is_safe_path(self, path: Path) -> bool:
        """Check that resolved path is within project root."""
        try:
            path.relative_to(self._project_root)
            return True
        except ValueError:
            return False

    def _get_header_context(self, header_path: Path) -> str:
        """Get non-function context from a header file (cached)."""
        if header_path in self._cache:
            return self._cache[header_path]

        try:
            raw = header_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Failed to read header: %s", header_path)
            self._cache[header_path] = ""
            return ""

        processed, _, _ = self._preprocessor.process(raw)
        chunks = split_functions(processed)

        parts: list[str] = []
        for chunk in chunks:
            stripped = chunk.code.strip()
            if not chunk.is_function and stripped:
                parts.append(stripped)

        context = "\n".join(parts)
        self._cache[header_path] = context
        return context
