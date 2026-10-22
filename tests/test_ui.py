"""Tests for console output and input (ui.py)."""

import logging

import pytest
from colorama import Fore

import ui as ui_module
from models import Flashcard
from quiz_engine import SessionStats
from tests.conftest import FakeInput
from ui import ConsoleUI, UIWarningHandler, format_table, shorten
from utils.stats_store import DeckSummary


@pytest.fixture
def plain() -> ConsoleUI:
    """Return a UI without colors."""
    return ConsoleUI(use_color=False)


def test_format_table_aligns_columns() -> None:
    lines = format_table([["a", "1"], ["long label", "22"]])

    assert lines == ["a           1", "long label  22"]


def test_format_table_with_no_rows_is_empty() -> None:
    assert format_table([]) == []


def test_shorten_keeps_short_text_and_cuts_long_text() -> None:
    assert shorten("short", 10) == "short"
    assert shorten("a" * 20, 10) == "aaaaaaa..."


def test_color_ui_prepares_windows_console(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        ui_module, "just_fix_windows_console", lambda: calls.append("called")
    )

    ConsoleUI(use_color=True)
    ConsoleUI(use_color=False)

    assert len(calls) == 1


def test_correct_result_is_green(capsys: pytest.CaptureFixture[str]) -> None:
    ConsoleUI(use_color=True).show_result(True, "def")

    assert Fore.GREEN + "Correct!" in capsys.readouterr().out


def test_incorrect_result_is_red_and_shows_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConsoleUI(use_color=True).show_result(False, "def")

    assert Fore.RED + "Incorrect — answer: def" in capsys.readouterr().out


def test_no_color_output_has_no_escape_codes(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    plain.show_result(True, "x")
    plain.show_result(False, "x")
    plain.show_question(1, Flashcard("Q", "A"))
    plain.show_summary(SessionStats(total=1, correct=1))
    plain.show_warning("careful")

    captured = capsys.readouterr()
    assert "\x1b[" not in captured.out + captured.err


def test_show_question_numbers_the_card(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    plain.show_question(4, Flashcard("DNS", "Domain Name System"))

    assert "Question 4: DNS" in capsys.readouterr().out


@pytest.mark.parametrize("limit, expected", [(None, "Cards: 10\n"), (3, "Limit: 3")])
def test_show_welcome(
    plain: ConsoleUI,
    capsys: pytest.CaptureFixture[str],
    limit: int | None,
    expected: str,
) -> None:
    plain.show_welcome("glossary.json", "random", 10, limit)

    out = capsys.readouterr().out
    assert "Flashcard Quizzer - glossary.json" in out
    assert expected in out
    assert '"exit"' in out


def test_summary_table_lists_every_missed_term(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    plain.show_summary(SessionStats(total=3, correct=1, missed=["CPU", "DNS"]))

    lines = capsys.readouterr().out.splitlines()
    assert "Total Questions  3" in lines
    assert "Correct          1" in lines
    assert "Accuracy         33.3%" in lines
    assert "Missed terms     CPU" in lines
    assert "                 DNS" in lines


def test_summary_with_nothing_missed(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    plain.show_summary(SessionStats())

    out = capsys.readouterr().out
    assert "Accuracy         0.0%" in out
    assert "(none)" in out


def test_ended_early_notice(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    plain.show_ended_early()

    assert "Quiz ended early" in capsys.readouterr().out


def test_lifetime_stats_table(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    summaries = [
        DeckSummary("glossary.json", 2, 20, 15, ["CPU", "DNS"]),
        DeckSummary("other.json", 1, 5, 5, []),
    ]

    plain.show_lifetime_stats(summaries, "history.json")

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Lifetime Stats (history.json)"
    assert lines[1].startswith("Deck ")
    assert lines[2].split()[:5] == ["glossary.json", "2", "20", "15", "75.0%"]
    assert lines[2].endswith("CPU, DNS")
    assert lines[3].endswith("-")


def test_lifetime_stats_without_history(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    plain.show_lifetime_stats([], "history.json")

    assert "No quiz history yet" in capsys.readouterr().out


def test_messages_go_to_the_right_stream(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    plain.show_info("hello")
    plain.show_warning("careful")
    plain.show_error("broken")

    captured = capsys.readouterr()
    assert captured.out == "hello\n"
    assert captured.err == "Warning: careful\nError: broken\n"


def test_ask_uses_input(plain: ConsoleUI, fake_input: FakeInput) -> None:
    prompts = fake_input("my answer")

    assert plain.ask("Your answer: ") == "my answer"
    assert prompts == ["Your answer: "]


def test_warning_handler_shows_warnings_but_not_errors(
    plain: ConsoleUI, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = logging.getLogger("test_ui_handler")
    handler = UIWarningHandler(plain)
    logger.addHandler(handler)
    try:
        logger.info("just info")
        logger.warning("watch out %s", "now")
        logger.error("already reported elsewhere")
    finally:
        logger.removeHandler(handler)

    assert capsys.readouterr().err == "Warning: watch out now\n"
