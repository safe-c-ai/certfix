"""Core modules for certfix."""

from certfix.core.detector import Detector
from certfix.core.fixer import Fixer
from certfix.core.include_resolver import IncludeResolver
from certfix.core.preprocessor import Preprocessor
from certfix.core.splitter import Chunk, split_functions
from certfix.core.validation import (
    aggregate_final_status,
    run_compile_check,
    run_semantic_check,
    run_violation_removal_check,
)

__all__ = [
    "Chunk",
    "Detector",
    "Fixer",
    "IncludeResolver",
    "Preprocessor",
    "aggregate_final_status",
    "run_compile_check",
    "run_semantic_check",
    "run_violation_removal_check",
    "split_functions",
]
