"""Shared pytest fixtures for the Flashcard Quizzer test suite."""

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from models import Flashcard

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

FakeInput = Callable[..., list[str]]


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point ``Path.home()`` at a temp folder so tests never touch real history."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def write_json(tmp_path: Path) -> Callable[..., Path]:
    """Return a helper that writes a value as JSON into a temporary file."""

    def _write(data: Any, name: str = "deck.json") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_text(tmp_path: Path) -> Callable[..., Path]:
    """Return a helper that writes raw text into a temporary file."""

    def _write(text: str, name: str = "deck.json") -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def data_dir() -> Path:
    """Return the path of the bundled ``data/`` folder."""
    return DATA_DIR


@pytest.fixture
def sample_cards() -> list[Flashcard]:
    """Return a small deck of three distinct cards."""
    return [
        Flashcard("API", "Application Programming Interface"),
        Flashcard("CPU", "Central Processing Unit"),
        Flashcard("DNS", "Domain Name System"),
    ]


@pytest.fixture
def deck_file(write_json: Callable[..., Path], sample_cards: list[Flashcard]) -> Path:
    """Write ``sample_cards`` to a temporary deck file and return its path."""
    return write_json([{"front": c.front, "back": c.back} for c in sample_cards])


@pytest.fixture
def history_file(tmp_path: Path) -> Path:
    """Return a path for a temporary quiz history file (not created yet)."""
    return tmp_path / "history.json"


@pytest.fixture
def fake_input(monkeypatch: pytest.MonkeyPatch) -> FakeInput:
    """Return a helper that replaces ``input()`` with scripted answers.

    Each answer is either a string to return or an exception to raise (e.g.
    ``KeyboardInterrupt()``). When the answers run out, ``EOFError`` is raised,
    just like real input reaching the end of a pipe. The helper returns the
    list of prompts that were shown.
    """

    def _install(*answers: str | BaseException) -> list[str]:
        prompts: list[str] = []
        queue = list(answers)

        def _input(prompt: str = "") -> str:
            prompts.append(prompt)
            if not queue:
                raise EOFError
            answer = queue.pop(0)
            if isinstance(answer, BaseException):
                raise answer
            return answer

        monkeypatch.setattr("builtins.input", _input)
        return prompts

    return _install
