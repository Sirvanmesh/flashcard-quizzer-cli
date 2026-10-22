"""End-to-end tests: the CLI from argument parsing to the printed summary."""

import io
import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

import main as cli
from data_loader import load_flashcards
from main import main
from quiz_engine import QuizModeFactory, QuizSession
from tests.conftest import PROJECT_ROOT, FakeInput
from ui import ConsoleUI

WriteJson = Callable[..., Path]

ALL_CORRECT = (
    "Application Programming Interface",
    "Central Processing Unit",
    "Domain Name System",
)


def run_cli(deck: Path, history: Path, *extra: str) -> int:
    """Run ``main`` on ``deck`` with an isolated history file."""
    return main(["-f", str(deck), "--history-file", str(history), *extra])


def test_full_session(
    deck_file: Path, fake_input: FakeInput, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_input("Application Programming Interface", "wrong", "domain  name system")
    cards = load_flashcards(deck_file)
    ui = ConsoleUI(use_color=False)
    mode = QuizModeFactory.create("sequential", cards)

    stats = QuizSession(mode, ui.ask, ui).run()
    ui.show_summary(stats)

    assert stats.total == 3
    assert stats.correct == 2
    assert stats.accuracy == 66.7
    assert stats.missed == ["CPU"]
    out = capsys.readouterr().out
    assert out.count("Correct!") == 2
    assert "Incorrect — answer: Central Processing Unit" in out
    assert "66.7%" in out


def test_main_full_game_prints_summary_and_saves_history(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input("Application Programming Interface", "nope", "Domain Name System")

    assert run_cli(deck_file, history_file) == 0

    out = capsys.readouterr().out
    assert "Quiz Summary" in out
    assert "Quiz ended early" not in out
    saved = json.loads(history_file.read_text(encoding="utf-8"))
    (record,) = saved["decks"].values()
    assert record["misses"] == {"CPU": 1}
    assert record["sessions"][0]["total"] == 3
    assert history_file.with_suffix(".log").read_text(encoding="utf-8")


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0

    out = capsys.readouterr().out
    assert "usage:" in out
    for flag in ("--file", "--mode", "--stats", "--limit", "--no-color", "--seed"):
        assert flag in out


def test_cli_missing_file_returns_1_no_traceback(
    tmp_path: Path, history_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli(tmp_path / "missing.json", history_file) == 1

    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    assert "Error: Could not load deck: File not found" in captured.err
    assert captured.err.count("Could not load deck") == 1  # shown once, not twice


def test_cli_invalid_deck_returns_1(
    write_json: WriteJson, history_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deck = write_json([{"front": "a", "back": "b"}, {"front": "c"}])

    assert run_cli(deck, history_file) == 1
    assert 'Card 2: missing required field "back"' in capsys.readouterr().err


def test_cli_without_file_or_stats_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 2
    assert "-f/--file" in capsys.readouterr().err


def test_exit_command_ends_quiz(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input("Application Programming Interface", "ExIt")

    assert run_cli(deck_file, history_file) == 0

    out = capsys.readouterr().out
    assert "Quiz ended early" in out
    assert "Question 3" not in out
    assert "Total Questions  1" in out


def test_keyboard_interrupt_ends_quiz(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input("wrong", KeyboardInterrupt())

    assert run_cli(deck_file, history_file) == 0

    captured = capsys.readouterr()
    assert "Quiz ended early" in captured.out
    assert "Total Questions  1" in captured.out
    assert "Traceback" not in captured.out + captured.err


def test_eof_ends_quiz(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input()  # no answers at all: the first input() raises EOFError

    assert run_cli(deck_file, history_file) == 0

    out = capsys.readouterr().out
    assert "Quiz ended early" in out
    assert "Total Questions  0" in out
    assert not history_file.exists()  # empty sessions are not recorded


def test_keyboard_interrupt_outside_quiz_returns_130(
    deck_file: Path,
    history_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupted_load(path: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "load_flashcards", interrupted_load)

    assert run_cli(deck_file, history_file) == 130
    assert "Interrupted." in capsys.readouterr().err


def test_stats_flag(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input("Application Programming Interface", "x", "y")
    run_cli(deck_file, history_file)
    capsys.readouterr()

    assert main(["--stats", "--history-file", str(history_file)]) == 0

    out = capsys.readouterr().out
    assert "Lifetime Stats" in out
    assert "deck.json" in out
    assert "33.3%" in out
    assert "CPU, DNS" in out


def test_stats_flag_with_no_history(
    history_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--stats", "--history-file", str(history_file)]) == 0
    assert "No quiz history yet" in capsys.readouterr().out


def test_limit_flag(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prompts = fake_input(*ALL_CORRECT)

    assert run_cli(deck_file, history_file, "--limit", "2") == 0

    assert len(prompts) == 2
    assert "Total Questions  2" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_invalid_limit(
    deck_file: Path,
    history_file: Path,
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_cli(deck_file, history_file, "--limit", value) == 2
    assert "argument --limit" in capsys.readouterr().err


def test_invalid_mode_is_rejected(
    deck_file: Path, history_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli(deck_file, history_file, "--mode", "spaced") == 2
    assert "invalid choice" in capsys.readouterr().err


def test_mode_flag_is_case_insensitive(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input("exit")

    assert run_cli(deck_file, history_file, "-m", "ADAPTIVE") == 0
    assert "Mode: adaptive" in capsys.readouterr().out


def test_random_mode_with_seed_is_repeatable(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    orders = []
    for _ in range(2):
        fake_input("a", "b", "c")
        run_cli(deck_file, history_file, "-m", "random", "--seed", "5")
        out = capsys.readouterr().out
        orders.append([line for line in out.splitlines() if "Question" in line])

    assert orders[0] == orders[1]


def test_seed_without_random_mode_warns(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input("exit")

    run_cli(deck_file, history_file, "--seed", "1")

    assert "--seed only applies to random mode" in capsys.readouterr().err


def test_adaptive_mode_asks_previously_missed_card_first(
    deck_file: Path,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input("Application Programming Interface", "wrong", "Domain Name System")
    run_cli(deck_file, history_file)
    capsys.readouterr()

    fake_input("exit")
    run_cli(deck_file, history_file, "-m", "adaptive")

    assert "Question 1: CPU" in capsys.readouterr().out


def test_duplicate_fronts_show_a_warning(
    write_json: WriteJson,
    history_file: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deck = write_json([{"front": "A", "back": "1"}, {"front": "a", "back": "2"}])
    fake_input("exit")

    assert run_cli(deck, history_file) == 0
    assert 'Warning: Duplicate card front "a"' in capsys.readouterr().err


def test_export_missed_writes_reloadable_deck(
    deck_file: Path,
    history_file: Path,
    tmp_path: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    export = tmp_path / "missed.json"
    fake_input("x", "Central Processing Unit", "y")

    assert run_cli(deck_file, history_file, "--export-missed", str(export)) == 0

    assert [card.front for card in load_flashcards(export)] == ["API", "DNS"]
    assert "Exported 2 missed card(s)" in capsys.readouterr().out


def test_export_missed_with_nothing_missed(
    deck_file: Path,
    history_file: Path,
    tmp_path: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    export = tmp_path / "missed.json"
    fake_input(*ALL_CORRECT)

    assert run_cli(deck_file, history_file, "--export-missed", str(export)) == 0

    assert not export.exists()
    assert "No missed cards to export." in capsys.readouterr().out


def test_export_missed_refuses_to_overwrite_the_deck(
    deck_file: Path, history_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = deck_file.read_text(encoding="utf-8")

    assert run_cli(deck_file, history_file, "--export-missed", str(deck_file)) == 1

    assert deck_file.read_text(encoding="utf-8") == original
    assert "must not overwrite the deck" in capsys.readouterr().err


def test_export_missed_bad_path_returns_1(
    deck_file: Path,
    history_file: Path,
    tmp_path: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_input("wrong")

    code = run_cli(
        deck_file, history_file, "--export-missed", str(tmp_path / "missed.txt")
    )

    assert code == 1
    assert "Could not export missed cards" in capsys.readouterr().err


def test_unwritable_history_folder_only_warns(
    deck_file: Path,
    tmp_path: Path,
    fake_input: FakeInput,
    capsys: pytest.CaptureFixture[str],
) -> None:
    history = tmp_path / "no_such_folder" / "history.json"
    fake_input(*ALL_CORRECT)

    assert run_cli(deck_file, history) == 0

    err = capsys.readouterr().err
    assert "Logging to file is disabled" in err
    assert "Could not save quiz history" in err


def test_should_use_color_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTerminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdout", FakeTerminal())
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli._should_use_color(no_color_flag=False)
    assert not cli._should_use_color(no_color_flag=True)

    monkeypatch.setenv("NO_COLOR", "1")
    assert not cli._should_use_color(no_color_flag=False)


def test_piped_output_is_switched_to_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeConsole(io.TextIOWrapper):
        def isatty(self) -> bool:
            return True

    piped = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    console = FakeConsole(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", piped)
    monkeypatch.setattr(sys, "stderr", console)

    cli._make_output_streams_safe()

    assert (piped.encoding, piped.errors) == ("utf-8", "replace")
    assert (console.encoding, console.errors) == ("cp1252", "replace")


def test_running_main_as_script_exits_with_main_return_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["main.py", "--help"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(PROJECT_ROOT / "main.py"), run_name="__main__")

    assert exit_info.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_real_process_with_piped_answers(deck_file: Path, history_file: Path) -> None:
    result = subprocess.run(
        [sys.executable, "main.py", "-f", str(deck_file)]
        + ["--history-file", str(history_file)],
        input="Application Programming Interface\nwrong\n",
        capture_output=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        timeout=60,
    )

    assert result.returncode == 0
    assert "Incorrect — answer: Central Processing Unit" in result.stdout
    assert "Quiz ended early" in result.stdout  # input ran out (EOF)
    assert "Traceback" not in result.stdout + result.stderr
