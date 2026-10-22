"""Tests for the persistent quiz history (utils/stats_store.py)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from utils.file_handler import JSONFileError
from utils.stats_store import (
    DeckSummary,
    StatsStore,
    default_history_path,
)


def test_default_history_path_is_in_home_folder(isolated_home: Path) -> None:
    assert default_history_path() == isolated_home / ".quiz_history.json"


def test_missing_history_file_starts_empty(history_file: Path) -> None:
    store = StatsStore(history_file)

    assert store.summaries() == []
    assert store.misses_for("any deck") == {}
    assert not history_file.exists()


def test_record_session_saves_and_reloads(history_file: Path) -> None:
    StatsStore(history_file).record_session("deck.json", "adaptive", 4, 3, ["CPU"])

    reloaded = StatsStore(history_file)

    assert reloaded.misses_for("deck.json") == {"CPU": 1}
    data = json.loads(history_file.read_text(encoding="utf-8"))
    session = data["decks"]["deck.json"]["sessions"][0]
    assert (session["mode"], session["total"], session["correct"]) == ("adaptive", 4, 3)
    assert "date" in session


def test_miss_counts_accumulate_across_sessions(history_file: Path) -> None:
    store = StatsStore(history_file)
    store.record_session("d.json", "sequential", 3, 1, ["CPU", "DNS"])
    store.record_session("d.json", "adaptive", 3, 2, ["CPU"])

    assert store.misses_for("d.json") == {"CPU": 2, "DNS": 1}


def test_misses_for_returns_a_copy(history_file: Path) -> None:
    store = StatsStore(history_file)
    store.record_session("d.json", "sequential", 1, 0, ["CPU"])

    store.misses_for("d.json")["CPU"] = 99

    assert store.misses_for("d.json") == {"CPU": 1}


def test_summaries_per_deck(history_file: Path) -> None:
    store = StatsStore(history_file)
    store.record_session("/decks/b.json", "random", 4, 2, ["x", "y", "z", "w"])
    store.record_session("/decks/b.json", "random", 4, 3, ["y"])
    store.record_session("/decks/A.json", "sequential", 2, 2, [])

    summaries = store.summaries()

    assert [s.name for s in summaries] == ["A.json", "b.json"]  # sorted by name
    deck_b = summaries[1]
    assert (deck_b.sessions, deck_b.questions, deck_b.correct) == (2, 8, 5)
    assert deck_b.accuracy == 62.5
    # Most missed first, ties alphabetically, at most three.
    assert deck_b.most_missed == ["y", "w", "x"]


def test_deck_summary_accuracy_with_no_questions() -> None:
    assert DeckSummary("d.json", 0, 0, 0, []).accuracy == 0.0


def test_corrupt_history_is_backed_up_and_replaced(
    history_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    history_file.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        store = StatsStore(history_file)

    assert store.summaries() == []
    assert "starting fresh" in caplog.text
    backup = history_file.with_name("history.json.bak")
    assert backup.read_text(encoding="utf-8") == "{not json"

    store.record_session("d.json", "sequential", 1, 1, [])
    assert StatsStore(history_file).summaries()[0].sessions == 1


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"version": 1},
        {"decks": []},
        {"decks": {"d": "not a dict"}},
        {"decks": {"d": {"sessions": {}, "misses": {}}}},
        {"decks": {"d": {"sessions": [], "misses": []}}},
        {"decks": {"d": {"sessions": ["x"], "misses": {}}}},
        {"decks": {"d": {"sessions": [{"total": "3", "correct": 1}], "misses": {}}}},
        {"decks": {"d": {"sessions": [{"total": 3, "correct": True}], "misses": {}}}},
        {"decks": {"d": {"sessions": [], "misses": {"CPU": -1}}}},
    ],
)
def test_history_with_unexpected_structure_starts_fresh(
    history_file: Path, data: Any, caplog: pytest.LogCaptureFixture
) -> None:
    history_file.write_text(json.dumps(data), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        store = StatsStore(history_file)

    assert store.summaries() == []
    assert "unexpected format" in caplog.text


def test_valid_history_is_loaded(history_file: Path) -> None:
    data = {
        "version": 1,
        "decks": {
            "d.json": {
                "sessions": [{"date": "x", "mode": "random", "total": 2, "correct": 1}],
                "misses": {"CPU": 1},
            }
        },
    }
    history_file.write_text(json.dumps(data), encoding="utf-8")

    assert StatsStore(history_file).misses_for("d.json") == {"CPU": 1}


def test_backup_failure_is_reported(
    history_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    history_file.write_text("oops", encoding="utf-8")

    def refuse(self: Path, target: Path) -> Path:
        raise OSError("locked")

    monkeypatch.setattr(Path, "replace", refuse)

    with caplog.at_level(logging.WARNING):
        StatsStore(history_file)

    assert "could not be backed up" in caplog.text


def test_save_to_missing_folder_raises(tmp_path: Path) -> None:
    store = StatsStore(tmp_path / "missing" / "history.json")

    with pytest.raises(JSONFileError, match="Could not write"):
        store.record_session("d.json", "sequential", 1, 1, [])


def test_path_property(history_file: Path) -> None:
    assert StatsStore(history_file).path == history_file
