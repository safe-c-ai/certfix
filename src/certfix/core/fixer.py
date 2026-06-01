"""CERT-C violation fixer."""

import subprocess
from pathlib import Path

from certfix.core.preprocessor import Preprocessor
from certfix.inference.base import InferenceBackend
from certfix.models import FixResult, Violation


class Fixer:
    """Fixer for CERT-C violations."""

    def __init__(
        self,
        backend: InferenceBackend,
        preprocessor: Preprocessor | None = None,
    ) -> None:
        """Initialize fixer.

        Args:
            backend: Inference backend for LLM.
            preprocessor: Code preprocessor. If None, creates default.
        """
        self.backend = backend
        self.preprocessor = preprocessor or Preprocessor()

    def fix_violation(
        self,
        violation: Violation,
        code: str,
    ) -> FixResult:
        """Generate fix for a single violation.

        Args:
            violation: The violation to fix.
            code: Original source code.

        Returns:
            Fix result with diff.
        """
        try:
            fixed_code = self.backend.fix(code, violation)
            return FixResult(
                violation=violation,
                original_code=code,
                fixed_code=fixed_code,
                success=True,
            )
        except Exception as e:
            return FixResult(
                violation=violation,
                original_code=code,
                fixed_code=code,
                success=False,
                error_message=str(e),
            )

    def verify_fix(
        self,
        fix: FixResult,
        cflags: str | None = None,
    ) -> bool:
        """Verify fix compiles correctly.

        Args:
            fix: Fix result to verify.
            cflags: Additional compiler flags.

        Returns:
            True if verification passes.
        """
        if not fix.success:
            return False

        # Write to temp file and compile
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
            f.write(fix.fixed_code)
            temp_path = f.name

        try:
            cmd = ["gcc", "-fsyntax-only"]
            if cflags:
                cmd.extend(cflags.split())
            cmd.append(temp_path)

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)
