"""Quiz logic: question-ordering strategies, their factory and the session.

Design patterns:

* **Strategy** - :class:`QuizMode` is the interface; :class:`SequentialMode`,
  :class:`RandomMode` and :class:`AdaptiveMode` are interchangeable
  algorithms for choosing the next card.
* **Factory** - :class:`QuizModeFactory` turns the ``--mode`` name into the
  right strategy, so callers never name a concrete class.

This module never prints or reads from the console. :class:`QuizSession`
receives an input function and a :class:`QuizOutput` object instead, which
keeps it easy to test.
"""

import random
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

from models import Flashcard

EXIT_COMMAND = "exit"


def normalize_answer(text: str) -> str:
    """Normalize an answer for comparison.

    Strips surrounding whitespace, collapses internal runs of whitespace to a
    single space and ignores case.

    Args:
        text: Raw answer text.

    Returns:
        The normalized text.
    """
    return " ".join(text.split()).casefold()


def is_correct(user_answer: str, expected: str) -> bool:
    """Check whether the user's answer matches the expected answer.

    Args:
        user_answer: What the user typed.
        expected: The back of the card.

    Returns:
        True if both match after :func:`normalize_answer`.
    """
    return normalize_answer(user_answer) == normalize_answer(expected)


class QuizMode(ABC):
    """Strategy interface: decides which card is asked next."""

    def __init__(self, cards: Sequence[Flashcard]) -> None:
        """Store a private copy of the deck.

        Args:
            cards: The deck to quiz on. The caller's sequence is never changed.

        Raises:
            ValueError: If the deck is empty.
        """
        if not cards:
            raise ValueError("A quiz needs at least one card.")
        self._cards: list[Flashcard] = list(cards)

    @abstractmethod
    def next_card(self) -> Flashcard | None:
        """Return the next card to ask, or None when the quiz is over."""

    @abstractmethod
    def record_answer(self, card: Flashcard, correct: bool) -> None:
        """Tell the strategy how the user answered ``card``.

        Args:
            card: The card that was just asked.
            correct: Whether the answer was correct.
        """


class SequentialMode(QuizMode):
    """Ask every card once, in deck order."""

    def __init__(self, cards: Sequence[Flashcard]) -> None:
        """Prepare to walk through the deck from the first card.

        Args:
            cards: The deck to quiz on.
        """
        super().__init__(cards)
        self._position = 0

    def next_card(self) -> Flashcard | None:
        """Return the next card in deck order, or None at the end."""
        if self._position >= len(self._cards):
            return None
        card = self._cards[self._position]
        self._position += 1
        return card

    def record_answer(self, card: Flashcard, correct: bool) -> None:
        """Ignore the answer: the order does not depend on it.

        Args:
            card: The card that was just asked.
            correct: Whether the answer was correct.
        """


class RandomMode(SequentialMode):
    """Ask every card once, in shuffled order.

    This is sequential mode over a shuffled private copy of the deck, so it
    reuses :meth:`SequentialMode.next_card` and ``record_answer``.
    """

    def __init__(self, cards: Sequence[Flashcard], seed: int | None = None) -> None:
        """Shuffle a copy of the deck.

        Args:
            cards: The deck to quiz on. It is copied, never shuffled in place.
            seed: Optional seed for a repeatable order (useful in tests).
        """
        super().__init__(cards)
        # Card order is not a security concern, and a seedable PRNG is needed
        # for repeatable --seed runs, so bandit's B311 warning does not apply.
        random.Random(seed).shuffle(self._cards)  # nosec B311


class AdaptiveMode(QuizMode):
    """Prioritize cards the user gets wrong.

    * Cards missed most often in earlier sessions (``history``) come first.
    * A card answered wrongly is put back into the queue ``requeue_gap``
      positions later (or at the end if fewer cards remain), so it is asked
      again in the same session.
    * Each card is re-asked at most ``max_repeats`` times, so the quiz always
      ends even if the user never gets it right.
    """

    def __init__(
        self,
        cards: Sequence[Flashcard],
        history: dict[str, int] | None = None,
        requeue_gap: int = 2,
        max_repeats: int = 3,
    ) -> None:
        """Order the deck by past misses and set up the re-queue rules.

        Args:
            cards: The deck to quiz on.
            history: Miss counts per card front from earlier sessions.
            requeue_gap: How many other cards to ask before a missed card
                comes back.
            max_repeats: Maximum number of times one card is re-asked.

        Raises:
            ValueError: If ``requeue_gap`` or ``max_repeats`` is negative.
        """
        super().__init__(cards)
        if requeue_gap < 0 or max_repeats < 0:
            raise ValueError("requeue_gap and max_repeats must not be negative.")
        misses = history or {}
        # sorted() is stable, so cards with equal miss counts keep deck order.
        ordered = sorted(self._cards, key=lambda card: -misses.get(card.front, 0))
        self._queue: deque[Flashcard] = deque(ordered)
        self._repeats: dict[Flashcard, int] = {}
        self._requeue_gap = requeue_gap
        self._max_repeats = max_repeats

    def next_card(self) -> Flashcard | None:
        """Return the card at the front of the queue, or None when empty."""
        return self._queue.popleft() if self._queue else None

    def record_answer(self, card: Flashcard, correct: bool) -> None:
        """Re-queue a missed card unless it has used up its repeats.

        Args:
            card: The card that was just asked.
            correct: Whether the answer was correct.
        """
        if correct:
            return
        repeats = self._repeats.get(card, 0)
        if repeats >= self._max_repeats:
            return
        self._repeats[card] = repeats + 1
        self._queue.insert(min(self._requeue_gap, len(self._queue)), card)


class QuizModeFactory:
    """Factory: create a quiz mode strategy from its name.

    Adding a new mode (for example spaced repetition) only needs a new
    :class:`QuizMode` subclass and one line in ``_registry``.
    """

    _registry: dict[str, type[QuizMode]] = {
        "sequential": SequentialMode,
        "random": RandomMode,
        "adaptive": AdaptiveMode,
    }

    @classmethod
    def available_modes(cls) -> list[str]:
        """Return the registered mode names in a stable order."""
        return list(cls._registry)

    @classmethod
    def create(cls, name: str, cards: Sequence[Flashcard], **kwargs: Any) -> QuizMode:
        """Create the quiz mode registered under ``name``.

        Args:
            name: Mode name, case-insensitive (e.g. "Adaptive").
            cards: The deck to quiz on.
            **kwargs: Extra options for that mode (e.g. ``seed`` for random,
                ``history`` for adaptive).

        Returns:
            A ready-to-use quiz mode.

        Raises:
            ValueError: If no mode is registered under ``name``.
        """
        key = name.strip().lower()
        mode_class = cls._registry.get(key)
        if mode_class is None:
            valid = ", ".join(cls.available_modes())
            raise ValueError(f"Unknown quiz mode '{name}'. Valid modes: {valid}.")
        return mode_class(cards, **kwargs)


@dataclass
class SessionStats:
    """Results of one quiz session."""

    total: int = 0
    correct: int = 0
    missed: list[str] = field(default_factory=list)
    ended_early: bool = False

    @property
    def accuracy(self) -> float:
        """Percentage of correct answers, rounded to 1 decimal (0 if none)."""
        if self.total == 0:
            return 0.0
        return round(self.correct / self.total * 100, 1)

    def record(self, card: Flashcard, correct: bool) -> None:
        """Add one answered question to the totals.

        Args:
            card: The card that was asked.
            correct: Whether the answer was correct.
        """
        self.total += 1
        if correct:
            self.correct += 1
        elif card.front not in self.missed:
            self.missed.append(card.front)


class QuizOutput(Protocol):
    """What :class:`QuizSession` needs from the user interface."""

    def show_question(self, number: int, card: Flashcard) -> None:
        """Display question ``number`` (1-based) for ``card``."""

    def show_result(self, correct: bool, expected: str) -> None:
        """Display whether the answer was correct and the expected answer."""


class QuizSession:
    """Run one quiz: ask questions, check answers and collect stats."""

    def __init__(
        self,
        mode: QuizMode,
        ask: Callable[[str], str],
        output: QuizOutput,
        limit: int | None = None,
    ) -> None:
        """Set up a session.

        Args:
            mode: The strategy that picks the next card.
            ask: Function that shows a prompt and returns the user's answer
                (``input`` in the real app, a fake in tests).
            output: Object that displays questions and results.
            limit: Maximum number of questions to ask, or None for no limit.

        Raises:
            ValueError: If ``limit`` is less than 1.
        """
        if limit is not None and limit < 1:
            raise ValueError("limit must be a positive integer.")
        self._mode = mode
        self._ask = ask
        self._output = output
        self._limit = limit

    def run(self) -> SessionStats:
        """Ask questions until the deck, the limit or the user ends the quiz.

        Typing "exit" (any case), pressing Ctrl+C or sending EOF ends the
        quiz early; the stats then cover only the questions answered.

        Returns:
            The session's statistics.
        """
        stats = SessionStats()
        while self._limit is None or stats.total < self._limit:
            card = self._mode.next_card()
            if card is None:
                break
            self._output.show_question(stats.total + 1, card)
            try:
                answer = self._ask("Your answer: ")
            except (KeyboardInterrupt, EOFError):
                stats.ended_early = True
                break
            if normalize_answer(answer) == EXIT_COMMAND:
                stats.ended_early = True
                break
            correct = is_correct(answer, card.back)
            stats.record(card, correct)
            self._mode.record_answer(card, correct)
            self._output.show_result(correct, card.back)
        return stats
