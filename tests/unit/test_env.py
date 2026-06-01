"""Tests for .env loading."""

from __future__ import annotations

import os
from pathlib import Path

from certfix.env import load_dotenv


def test_load_dotenv_sets_missing_values(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
# comment
OPENROUTER_API_KEY=sk-test
export DEEPINFRA_API_KEY="deepinfra-test"
SINGLE_QUOTED='single-test'
NO_EQUALS
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.delenv("SINGLE_QUOTED", raising=False)

    loaded = load_dotenv(env_path)

    assert loaded == {
        "OPENROUTER_API_KEY": "sk-test",
        "DEEPINFRA_API_KEY": "deepinfra-test",
        "SINGLE_QUOTED": "single-test",
    }
    assert os.environ["OPENROUTER_API_KEY"] == "sk-test"
    assert os.environ["DEEPINFRA_API_KEY"] == "deepinfra-test"
    assert os.environ["SINGLE_QUOTED"] == "single-test"


def test_load_dotenv_does_not_override_existing_values(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")

    loaded = load_dotenv(env_path)

    assert loaded == {}
    assert os.environ["OPENROUTER_API_KEY"] == "from-env"


def test_load_dotenv_missing_file_is_noop(tmp_path: Path) -> None:
    assert load_dotenv(tmp_path / ".env") == {}
