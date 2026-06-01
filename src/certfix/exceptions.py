"""Custom exceptions for certfix."""


class CertfixError(Exception):
    """Base exception for certfix."""

    pass


class ModelNotFoundError(CertfixError):
    """Model file not found."""

    pass


class ModelLoadError(CertfixError):
    """Failed to load model."""

    pass


class InferenceError(CertfixError):
    """Inference failed."""

    pass


class TimeoutError(CertfixError):
    """Inference timeout."""

    pass


class ParseError(CertfixError):
    """Failed to parse C code."""

    pass


class ConfigError(CertfixError):
    """Configuration error."""

    pass
