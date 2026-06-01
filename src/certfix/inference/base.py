"""Base class for inference backends."""

from abc import ABC, abstractmethod

from certfix.exceptions import InferenceError
from certfix.models import Violation


class InferenceBackend(ABC):
    """Abstract base class for inference backends."""

    @abstractmethod
    def detect(self, code: str, rules: list[str] | None = None) -> list[Violation]:
        """Detect violations in code.

        Args:
            code: C source code to analyze.
            rules: List of rule IDs to check. If None, check all.

        Returns:
            List of detected violations.
        """
        pass

    @abstractmethod
    def fix(self, code: str, violation: Violation) -> str:
        """Generate fix for a violation.

        Args:
            code: Original C source code.
            violation: The violation to fix.

        Returns:
            Fixed source code.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend is available.

        Returns:
            True if backend can be used.
        """
        pass

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        stop: list[str] | None = None,
    ) -> str:
        """Generate raw text for stage-specific prompts."""
        raise InferenceError(f"{type(self).__name__} does not support raw text generation")
