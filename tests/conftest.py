"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def sample_c_code() -> str:
    """Sample C code with a violation."""
    return """
#include <stdio.h>

void func(void) {
    int *ptr;
    *ptr = 10;  // EXP33-C: Uninitialized pointer
}

int main(void) {
    func();
    return 0;
}
"""


@pytest.fixture
def sample_c_code_with_comments() -> str:
    """Sample C code with comments."""
    return """
#include <stdio.h>

// This function has a bug
void func(void) {
    int *ptr;  /* uninitialized */
    *ptr = 10;  // certfix:ignore EXP33-C
}

int main(void) {
    func();
    return 0;
}
"""


@pytest.fixture
def temp_c_file(tmp_path: Path, sample_c_code: str) -> Path:
    """Create a temporary C file."""
    c_file = tmp_path / "test.c"
    c_file.write_text(sample_c_code)
    return c_file
