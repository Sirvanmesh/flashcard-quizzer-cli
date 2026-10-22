"""Tests for the quiz strategies, the factory and QuizSession (quiz_engine.py)."""

from typing import Callable, Iterator

import pytest

from models import Flashcard
from quiz_engine import (
    AdaptiveMode,
    QuizMode,
    QuizModeFactory,
    QuizSession,
    RandomMode,
    SequentialMode,
    SessionStats,
    is_correct,
)


class RecordingOutput:
    """Fake QuizOutput that records what would have been displayed."""

    def __init__(self) -> None:
        """Start with no recorded questions or results."""
        self.questions: list[tuple[int, str]] = []
        self.results: list[tuple[bool, str]] = []

    def show_question(self, number: int, card: Flashcard) -> None:
        """Record the question number and front."""
        self.questions.append((number, card.front))

    def show_result(self, correct: bool, expected: str) -> None:
        """Record the result and expected answer."""
        self.results.append((correct, expected))


def scripted_input(*answers: str) -> Callable[[str], str]:
    """Return a fake ``input`` that replies with ``answers`` in order."""
    replies: Iterator[str] = iter(answers)
    return lambda prompt: next(replies)


def drain(mode: QuizMode, answer_correctly: bool = True) -> list[str]:
    """Ask every card of ``mode`` and return the fronts in the order asked."""
    asked: list[str] = []
    while (card := mode.next_card()) is not None:
        asked.append(card.front)
        mode.record_answer(card, answer_correctly)
    return asked


def make_deck(size: int) -> list[Flashcard]:
    """Return ``size`` distinct cards named c1..cN."""
    return [Flashcard(f"c{i}", f"answer {i}") for i in range(1, size + 1)]


# --- Factory -----------------------------------------------------------------


def test_quiz_mode_factory(sample_cards: list[Flashcard]) -> None:
    # Exact type checks: RandomMode subclasses SequentialMode, so isinstance
    # would not catch the factory returning the wrong one.
    assert type(QuizModeFactory.create("sequential", sample_cards)) is SequentialMode
    assert type(QuizModeFactory.create("random", sample_cards)) is RandomMode
    assert type(QuizModeFactory.create("adaptive", sample_cards)) is AdaptiveMode

    with pytest.raises(ValueError, match="Valid modes: sequential, random, adaptive"):
        QuizModeFactory.create("spaced", sample_cards)


@pytest.mark.parametrize("name", ["ADAPTIVE", " Adaptive ", "adaptive"])
def test_quiz_mode_factory_is_case_insensitive(
    sample_cards: list[Flashcard], name: str
) -> None:
    assert isinstance(QuizModeFactory.create(name, sample_cards), AdaptiveMode)


def test_quiz_mode_factory_passes_options_to_mode(
    sample_cards: list[Flashcard],
) -> None:
    mode = QuizModeFactory.create("random", sample_cards, seed=1)
    same = RandomMode(sample_cards, seed=1)

    assert drain(mode) == drain(same)


def test_quiz_mode_factory_lists_available_modes() -> None:
    assert QuizModeFactory.available_modes() == ["sequential", "random", "adaptive"]


def test_quiz_mode_rejects_empty_deck() -> None:
    with pytest.raises(ValueError, match="at least one card"):
        SequentialMode([])


# --- Sequential and random ---------------------------------------------------


def test_sequential_order(sample_cards: list[Flashcard]) -> None:
    assert drain(SequentialMode(sample_cards)) == ["API", "CPU", "DNS"]


def test_sequential_ignores_wrong_answers(sample_cards: list[Flashcard]) -> None:
    assert drain(SequentialMode(sample_cards), answer_correctly=False) == [
        "API",
        "CPU",
        "DNS",
    ]


def test_random_mode_same_cards_different_order_with_seed() -> None:
    deck = make_deck(10)

    first = drain(RandomMode(deck, seed=42))
    again = drain(RandomMode(deck, seed=42))

    assert first == again  # same seed -> same order
    assert sorted(first) == sorted(card.front for card in deck)  # same cards
    assert first != [card.front for card in deck]  # but shuffled


def test_random_mode_does_not_mutate_deck() -> None:
    deck = make_deck(10)
    original = list(deck)

    drain(RandomMode(deck, seed=3))

    assert deck == original


# --- Adaptive ----------------------------------------------------------------


def test_adaptive_mode_behavior() -> None:
    mode = AdaptiveMode(make_deck(4))

    first = mode.next_card()
    assert first is not None and first.front == "c1"
    mode.record_answer(first, correct=False)

    # The missed card comes back after two other cards.
    assert drain(mode) == ["c2", "c3", "c1", "c4"]


def test_adaptive_requeues_at_end_when_few_cards_remain() -> None:
    mode = AdaptiveMode(make_deck(2))

    first = mode.next_card()
    assert first is not None
    mode.record_answer(first, correct=False)

    # Only one card is left, so the missed card goes to the end of the queue.
    assert drain(mode) == ["c2", "c1"]


def test_adaptive_correct_answer_is_not_requeued() -> None:
    assert drain(AdaptiveMode(make_deck(3))) == ["c1", "c2", "c3"]


def test_adaptive_max_repeats_ends_quiz() -> None:
    mode = AdaptiveMode([Flashcard("hard", "x")], max_repeats=3)

    asked = drain(mode, answer_correctly=False)

    # Asked once, then re-asked at most 3 times: the quiz ends.
    assert asked == ["hard"] * 4


def test_adaptive_history_priority() -> None:
    deck = make_deck(4)
    history = {"c3": 5, "c2": 1, "unknown": 9}

    assert drain(AdaptiveMode(deck, history=history)) == ["c3", "c2", "c1", "c4"]


def test_adaptive_rejects_negative_settings() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        AdaptiveMode(make_deck(1), max_repeats=-1)


# --- Answer checking and stats -------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    ["def", "DEF", "  Def  ", "dEf\n"],
)
def test_answer_case_insensitive(answer: str) -> None:
    assert is_correct(answer, "def")


def test_answer_collapses_internal_whitespace() -> None:
    assert is_correct("domain   name\tsystem", "Domain Name System")


@pytest.mark.parametrize("answer", ["", "   ", "deff", "de f"])
def test_wrong_or_blank_answer_is_incorrect(answer: str) -> None:
    assert not is_correct(answer, "def")


def test_stats_zero_questions() -> None:
    stats = SessionStats()

    assert stats.total == 0
    assert stats.accuracy == 0.0
    assert stats.missed == []


def test_stats_accuracy_rounds_to_one_decimal() -> None:
    stats = SessionStats(total=3, correct=2)

    assert stats.accuracy == 66.7


def test_stats_missed_terms_are_unique_and_ordered() -> None:
    stats = SessionStats()
    a, b = Flashcard("a", "1"), Flashcard("b", "2")

    for card, correct in [(b, False), (a, False), (b, False), (a, True)]:
        stats.record(card, correct)

    assert stats.missed == ["b", "a"]
    assert (stats.total, stats.correct) == (4, 1)


# --- QuizSession ---------------------------------------------------------------


def test_session_counts_answers(sample_cards: list[Flashcard]) -> None:
    output = RecordingOutput()
    ask = scripted_input(
        "application programming interface", "wrong", "domain name system"
    )
    session = QuizSession(SequentialMode(sample_cards), ask, output)

    stats = session.run()

    assert (stats.total, stats.correct, stats.missed) == (3, 2, ["CPU"])
    assert not stats.ended_early
    assert output.questions == [(1, "API"), (2, "CPU"), (3, "DNS")]
    assert output.results[1] == (False, "Central Processing Unit")


def test_session_respects_limit(sample_cards: list[Flashcard]) -> None:
    session = QuizSession(
        SequentialMode(sample_cards), scripted_input("x", "y"), RecordingOutput(), 2
    )

    assert session.run().total == 2


@pytest.mark.parametrize("limit", [0, -3])
def test_session_rejects_non_positive_limit(
    sample_cards: list[Flashcard], limit: int
) -> None:
    with pytest.raises(ValueError, match="positive"):
        QuizSession(SequentialMode(sample_cards), input, RecordingOutput(), limit)


@pytest.mark.parametrize("command", ["exit", "EXIT", "  Exit "])
def test_session_exit_command_ends_early(
    sample_cards: list[Flashcard], command: str
) -> None:
    ask = scripted_input("Application Programming Interface", command)
    session = QuizSession(SequentialMode(sample_cards), ask, RecordingOutput())

    stats = session.run()

    assert stats.ended_early
    assert (stats.total, stats.correct) == (1, 1)


@pytest.mark.parametrize("error", [KeyboardInterrupt, EOFError])
def test_session_interrupt_or_eof_ends_early(
    sample_cards: list[Flashcard], error: type[BaseException]
) -> None:
    def ask(prompt: str) -> str:
        raise error

    stats = QuizSession(SequentialMode(sample_cards), ask, RecordingOutput()).run()

    assert stats.ended_early
    assert stats.total == 0


def test_session_with_adaptive_mode_reasks_missed_card() -> None:
    deck = make_deck(3)
    ask = scripted_input("wrong", "answer 2", "answer 3", "answer 1")
    output = RecordingOutput()

    stats = QuizSession(AdaptiveMode(deck), ask, output).run()

    assert [front for _, front in output.questions] == ["c1", "c2", "c3", "c1"]
    assert (stats.total, stats.correct, stats.missed) == (4, 3, ["c1"])
