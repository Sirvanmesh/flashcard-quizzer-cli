"""Entry point for the Flashcard Quizzer CLI.

Examples::

    python main.py --mode sequential --file data/glossary.json
    python main.py -m adaptive -f data/python_basics.json
    python main.py --stats
"""

import argparse
import io
import logging
import os
import sys
from pathlib import Path
from typing import Any

from data_loader import FlashcardLoadError, load_flashcards
from models import Flashcard
from quiz_engine import QuizModeFactory, QuizSession, SessionStats
from ui import ConsoleUI, UIWarningHandler
from utils.file_handler import JSONFileError, write_json_file
from utils.stats_store import StatsStore, default_history_path

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPTED = 130
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

EXAMPLES = """examples:
  python main.py --mode sequential --file data/glossary.json
  python main.py -m random -f data/glossary.json --seed 7 --limit 5
  python main.py -m adaptive -f data/python_basics.json --export-missed missed.json
  python main.py --stats
"""


def positive_int(text: str) -> int:
    """Parse a strictly positive integer for argparse.

    Args:
        text: The raw command-line value.

    Returns:
        The parsed integer.

    Raises:
        argparse.ArgumentTypeError: If ``text`` is not an integer above 0.
    """
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a positive number, got {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Quiz yourself with flashcards loaded from a JSON file.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-f", "--file", help="path to a JSON deck (required unless --stats is used)"
    )
    parser.add_argument(
        "-m",
        "--mode",
        type=str.lower,
        choices=QuizModeFactory.available_modes(),
        default="sequential",
        help="question order (default: sequential)",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        metavar="N",
        help="ask at most N questions",
    )
    parser.add_argument(
        "--seed", type=int, help="seed for a repeatable order in random mode"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="plain output without colors"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="show saved lifetime stats per deck and exit",
    )
    parser.add_argument(
        "--export-missed",
        metavar="PATH",
        help="save the cards you missed as a new .json deck",
    )
    parser.add_argument(
        "--history-file",
        type=Path,
        default=default_history_path(),
        metavar="PATH",
        help="quiz history file (default: %(default)s); "
        "the log file is written next to it",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Flashcard Quizzer.

    Args:
        argv: Command-line arguments without the program name. ``None``
            means ``sys.argv[1:]``.

    Returns:
        The process exit code: 0 on success (including a quiz ended early),
        1 on a deck or file error, 2 on invalid arguments and 130 if the
        program is interrupted outside a quiz.
    """
    _make_output_streams_safe()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if not args.stats and not args.file:
            parser.error("the following arguments are required: -f/--file")
    except SystemExit as exc:  # argparse exits on --help and on bad arguments
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR

    ui = ConsoleUI(use_color=_should_use_color(args.no_color))
    handlers = _configure_logging(args.history_file.with_suffix(".log"), ui)
    try:
        return _run(args, ui)
    except KeyboardInterrupt:
        ui.show_error("Interrupted.")
        return EXIT_INTERRUPTED
    finally:
        _remove_logging(handlers)


def _run(args: argparse.Namespace, ui: ConsoleUI) -> int:
    """Carry out the command described by the parsed arguments.

    Args:
        args: Parsed command-line arguments.
        ui: The console UI.

    Returns:
        The process exit code.
    """
    store = StatsStore(args.history_file)
    if args.stats:
        ui.show_lifetime_stats(store.summaries(), str(store.path))
        return EXIT_OK

    try:
        cards = load_flashcards(args.file)
    except FlashcardLoadError as exc:
        logger.error("Could not load deck %s: %s", args.file, exc)
        ui.show_error(f"Could not load deck: {exc}")
        return EXIT_ERROR

    deck_path = Path(args.file)
    deck_key = str(deck_path.resolve())
    logger.info("Loaded %d cards from %s", len(cards), deck_key)
    if args.export_missed and Path(args.export_missed).resolve() == Path(deck_key):
        ui.show_error("--export-missed must not overwrite the deck being played.")
        return EXIT_ERROR

    mode = QuizModeFactory.create(
        args.mode, cards, **_mode_options(args, store, deck_key, ui)
    )
    ui.show_welcome(deck_path.name, args.mode, len(cards), args.limit)
    stats = QuizSession(mode, ui.ask, ui, args.limit).run()

    if stats.ended_early:
        ui.show_ended_early()
    ui.show_summary(stats)
    logger.info(
        "Session finished: mode=%s total=%d correct=%d ended_early=%s",
        args.mode,
        stats.total,
        stats.correct,
        stats.ended_early,
    )
    _save_history(store, deck_key, args.mode, stats, ui)

    if args.export_missed:
        return _export_missed(cards, stats, args.export_missed, ui)
    return EXIT_OK


def _mode_options(
    args: argparse.Namespace, store: StatsStore, deck_key: str, ui: ConsoleUI
) -> dict[str, Any]:
    """Return the extra constructor options for the selected quiz mode.

    Args:
        args: Parsed command-line arguments.
        store: History store (adaptive mode uses past miss counts).
        deck_key: Key of the current deck in the history.
        ui: The console UI, for warnings about ignored options.

    Returns:
        Keyword arguments for :meth:`QuizModeFactory.create`.
    """
    if args.mode == "random":
        return {"seed": args.seed}
    if args.seed is not None:
        ui.show_warning("--seed only applies to random mode and was ignored.")
    if args.mode == "adaptive":
        return {"history": store.misses_for(deck_key)}
    return {}


def _save_history(
    store: StatsStore, deck_key: str, mode: str, stats: SessionStats, ui: ConsoleUI
) -> None:
    """Record the session in the history file, warning if that fails.

    Sessions with no answered questions are not recorded.

    Args:
        store: The history store.
        deck_key: Key of the current deck in the history.
        mode: Name of the quiz mode played.
        stats: The finished session's statistics.
        ui: The console UI.
    """
    if stats.total == 0:
        return
    try:
        store.record_session(
            deck_key, mode, stats.total, stats.correct, list(stats.missed)
        )
    except JSONFileError as exc:
        logger.warning("Could not save quiz history: %s", exc)


def _export_missed(
    cards: list[Flashcard], stats: SessionStats, path: str, ui: ConsoleUI
) -> int:
    """Write the missed cards to ``path`` as an array-format deck.

    Args:
        cards: The full deck.
        stats: The finished session's statistics.
        path: Destination ``.json`` file.
        ui: The console UI.

    Returns:
        The process exit code.
    """
    if not stats.missed:
        ui.show_info("No missed cards to export.")
        return EXIT_OK
    by_front: dict[str, Flashcard] = {}
    for card in cards:
        by_front.setdefault(card.front, card)
    missed_cards = [by_front[front] for front in stats.missed]
    try:
        write_json_file(
            path, [{"front": card.front, "back": card.back} for card in missed_cards]
        )
    except JSONFileError as exc:
        ui.show_error(f"Could not export missed cards: {exc}")
        return EXIT_ERROR
    ui.show_info(f"Exported {len(missed_cards)} missed card(s) to {path}")
    return EXIT_OK


def _should_use_color(no_color_flag: bool) -> bool:
    """Decide whether to color output.

    Colors are off with ``--no-color``, when the ``NO_COLOR`` environment
    variable is set (see no-color.org) or when output is not a terminal.

    Args:
        no_color_flag: Value of the ``--no-color`` option.

    Returns:
        True if output should be colored.
    """
    if no_color_flag or "NO_COLOR" in os.environ:
        return False
    return sys.stdout.isatty()


def _make_output_streams_safe() -> None:
    """Use UTF-8 for piped input/output and never crash on odd characters.

    On Windows, Python reads and writes pipes in the legacy code page
    (e.g. cp1252) while most tools expect UTF-8, so characters such as the
    em dash in "Incorrect — answer" came out garbled. Interactive consoles
    already use UTF-8 and are left alone.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if not isinstance(stream, io.TextIOWrapper):
            continue
        if stream.isatty():
            stream.reconfigure(errors="replace")
        else:
            stream.reconfigure(encoding="utf-8", errors="replace")


def _configure_logging(log_path: Path, ui: ConsoleUI) -> list[logging.Handler]:
    """Send all log records to a file and warnings to the UI.

    Args:
        log_path: File to append log records to.
        ui: The console UI that displays warnings.

    Returns:
        The handlers that were added, for :func:`_remove_logging`.
    """
    handlers: list[logging.Handler] = [UIWarningHandler(ui)]
    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError as exc:
        ui.show_warning(f"Logging to file is disabled ({exc.strerror}).")
    else:
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handlers.append(file_handler)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in handlers:
        root.addHandler(handler)
    return handlers


def _remove_logging(handlers: list[logging.Handler]) -> None:
    """Detach and close handlers added by :func:`_configure_logging`.

    Args:
        handlers: The handlers to remove.
    """
    root = logging.getLogger()
    for handler in handlers:
        root.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    sys.exit(main())
