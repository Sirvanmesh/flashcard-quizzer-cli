"""Persistent quiz history: past sessions and miss counts per deck.

The history is a small JSON file (by default ``~/.quiz_history.json``)::

    {
      "version": 1,
      "decks": {
        "C:/path/to/glossary.json": {
          "sessions": [{"date": "...", "mode": "adaptive",
                        "total": 10, "correct": 8}],
          "misses": {"CPU": 2, "DNS": 1}
        }
      }
    }

Adaptive mode reads the miss counts to ask the hardest cards first, and
``--stats`` summarizes the sessions.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.file_handler import JSONFileError, read_json_file, write_json_file

logger = logging.getLogger(__name__)

HISTORY_VERSION = 1
HISTORY_FILE_NAME = ".quiz_history.json"
MOST_MISSED_LIMIT = 3


def default_history_path() -> Path:
    """Return the default history file location in the user's home folder."""
    return Path.home() / HISTORY_FILE_NAME


@dataclass(frozen=True)
class DeckSummary:
    """Lifetime statistics for one deck."""

    name: str
    sessions: int
    questions: int
    correct: int
    most_missed: list[str]

    @property
    def accuracy(self) -> float:
        """Percentage of correct answers, rounded to 1 decimal (0 if none)."""
        if self.questions == 0:
            return 0.0
        return round(self.correct / self.questions * 100, 1)


class StatsStore:
    """Load, update and save the quiz history file."""

    def __init__(self, path: str | Path) -> None:
        """Open the history at ``path``, starting fresh if it is missing.

        A corrupt or unreadable history file is backed up next to the
        original (``.bak``) and replaced by an empty history, with a warning.

        Args:
            path: Location of the history JSON file.
        """
        self._path = Path(path)
        self._data = self._load()

    @property
    def path(self) -> Path:
        """Location of the history file."""
        return self._path

    def misses_for(self, deck: str) -> dict[str, int]:
        """Return the miss counts per card front for ``deck``.

        Args:
            deck: The deck key (see :meth:`record_session`).

        Returns:
            A copy of the miss counts (empty for an unknown deck).
        """
        return dict(self._data["decks"].get(deck, {}).get("misses", {}))

    def record_session(
        self, deck: str, mode: str, total: int, correct: int, missed: list[str]
    ) -> None:
        """Add one finished session to the history and save it.

        Args:
            deck: Key identifying the deck, e.g. its resolved file path.
            mode: Name of the quiz mode that was played.
            total: Number of questions answered.
            correct: Number of correct answers.
            missed: Fronts of the cards answered wrongly (each counted once).

        Raises:
            JSONFileError: If the history file cannot be written.
        """
        record = self._data["decks"].setdefault(deck, {"sessions": [], "misses": {}})
        record["sessions"].append(
            {
                "date": datetime.now().isoformat(timespec="seconds"),
                "mode": mode,
                "total": total,
                "correct": correct,
            }
        )
        misses: dict[str, int] = record["misses"]
        for front in missed:
            misses[front] = misses.get(front, 0) + 1
        self.save()

    def summaries(self) -> list[DeckSummary]:
        """Return lifetime statistics for every deck, sorted by deck name."""
        result = []
        for deck, record in self._data["decks"].items():
            sessions = record["sessions"]
            misses: dict[str, int] = record["misses"]
            ranked = sorted(misses, key=lambda front: (-misses[front], front))
            result.append(
                DeckSummary(
                    name=Path(deck).name,
                    sessions=len(sessions),
                    questions=sum(session["total"] for session in sessions),
                    correct=sum(session["correct"] for session in sessions),
                    most_missed=ranked[:MOST_MISSED_LIMIT],
                )
            )
        return sorted(result, key=lambda summary: summary.name.casefold())

    def save(self) -> None:
        """Write the history to disk atomically.

        Raises:
            JSONFileError: If the file cannot be written.
        """
        write_json_file(self._path, self._data)

    def _load(self) -> dict[str, Any]:
        """Read the history file, or return an empty history.

        Returns:
            The history data in the documented format.
        """
        if not self._path.exists():
            return _empty_history()
        try:
            data = read_json_file(self._path)
        except JSONFileError as exc:
            self._back_up_bad_file(str(exc))
            return _empty_history()
        if not _is_valid_history(data):
            self._back_up_bad_file("unexpected format")
            return _empty_history()
        return data

    def _back_up_bad_file(self, reason: str) -> None:
        """Move an unusable history file aside and log a warning.

        Args:
            reason: Why the file could not be used.
        """
        backup = self._path.with_name(self._path.name + ".bak")
        try:
            self._path.replace(backup)
            where = f"the old file was moved to {backup}"
        except OSError:
            where = "the old file could not be backed up"
        logger.warning(
            "History file %s is unusable (%s); starting fresh and %s.",
            self._path,
            reason,
            where,
        )


def _empty_history() -> dict[str, Any]:
    """Return a new, empty history structure."""
    return {"version": HISTORY_VERSION, "decks": {}}


def _is_count(value: Any) -> bool:
    """Return True if ``value`` is a non-negative int (bools excluded)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_valid_history(data: Any) -> bool:
    """Check that ``data`` has the documented history structure.

    Args:
        data: Parsed JSON from the history file.

    Returns:
        True if every deck has a list of sessions with integer counts and a
        mapping of fronts to integer miss counts.
    """
    if not isinstance(data, dict) or not isinstance(data.get("decks"), dict):
        return False
    for record in data["decks"].values():
        if not isinstance(record, dict):
            return False
        sessions = record.get("sessions")
        misses = record.get("misses")
        if not isinstance(sessions, list) or not isinstance(misses, dict):
            return False
        for session in sessions:
            if not isinstance(session, dict):
                return False
            if not (
                _is_count(session.get("total")) and _is_count(session.get("correct"))
            ):
                return False
        if not all(_is_count(count) for count in misses.values()):
            return False
    return True
