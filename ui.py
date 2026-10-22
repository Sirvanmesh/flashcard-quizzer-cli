"""All console input and output for the Flashcard Quizzer.

:class:`ConsoleUI` implements the ``QuizOutput`` protocol used by
``QuizSession`` and also prints the welcome banner, summaries and errors.
No other module prints to the console.
"""

import logging
import sys
from typing import Sequence

from colorama import Fore, Style, just_fix_windows_console

from models import Flashcard
from quiz_engine import SessionStats
from utils.stats_store import DeckSummary

MAX_CELL_WIDTH = 60


def format_table(rows: Sequence[Sequence[str]], gap: int = 2) -> list[str]:
    """Format rows of text as left-aligned columns.

    Args:
        rows: The table rows; every row should have the same number of cells.
        gap: Spaces between columns.

    Returns:
        One string per row, without trailing whitespace.
    """
    if not rows:
        return []
    widths = [max(len(row[col]) for row in rows) for col in range(len(rows[0]))]
    spacer = " " * gap
    return [
        spacer.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in rows
    ]


def shorten(text: str, width: int = MAX_CELL_WIDTH) -> str:
    """Cut ``text`` to ``width`` characters, ending with "..." if cut.

    Args:
        text: The text to shorten.
        width: Maximum length of the result (at least 4).

    Returns:
        The original text, or a shortened copy.
    """
    return text if len(text) <= width else text[: width - 3] + "..."


class ConsoleUI:
    """Console input/output with optional colors (via colorama)."""

    def __init__(self, use_color: bool = True) -> None:
        """Create the UI.

        Args:
            use_color: Whether to color output. When True, Windows consoles
                are prepared to understand ANSI color codes.
        """
        self._use_color = use_color
        if use_color:
            just_fix_windows_console()

    def ask(self, prompt: str) -> str:
        """Show ``prompt`` and return the line the user types.

        Raises:
            KeyboardInterrupt: If the user presses Ctrl+C.
            EOFError: If input ends (Ctrl+Z/Ctrl+D or end of piped input).
        """
        return input(prompt)

    def show_welcome(
        self, deck_name: str, mode: str, card_count: int, limit: int | None
    ) -> None:
        """Print the banner shown before the first question.

        Args:
            deck_name: File name of the deck.
            mode: Name of the quiz mode.
            card_count: Number of cards in the deck.
            limit: Question limit, or None.
        """
        details = f"Mode: {mode} | Cards: {card_count}"
        if limit is not None:
            details += f" | Limit: {limit}"
        print(self._paint(f"Flashcard Quizzer - {deck_name}", Style.BRIGHT))
        print(details)
        print('Type your answer and press Enter. Type "exit" to stop.')

    def show_question(self, number: int, card: Flashcard) -> None:
        """Print question ``number`` with the card's front.

        Args:
            number: 1-based question number.
            card: The card being asked.
        """
        print()
        print(self._paint(f"Question {number}:", Fore.CYAN) + f" {card.front}")

    def show_result(self, correct: bool, expected: str) -> None:
        """Print "Correct!" in green or the right answer in red.

        Args:
            correct: Whether the user's answer was correct.
            expected: The correct answer.
        """
        if correct:
            print(self._paint("Correct!", Fore.GREEN))
        else:
            print(self._paint(f"Incorrect — answer: {expected}", Fore.RED))

    def show_ended_early(self) -> None:
        """Print the notice shown when the user stops the quiz early."""
        print()
        print(self._paint("Quiz ended early", Fore.YELLOW))

    def show_summary(self, stats: SessionStats) -> None:
        """Print the end-of-quiz summary table.

        Args:
            stats: The finished session's statistics.
        """
        missed = stats.missed or ["(none)"]
        rows = [
            ["Total Questions", str(stats.total)],
            ["Correct", str(stats.correct)],
            ["Accuracy", f"{stats.accuracy:.1f}%"],
            ["Missed terms", missed[0]],
        ]
        rows.extend(["", term] for term in missed[1:])
        print()
        print(self._paint("Quiz Summary", Style.BRIGHT))
        for line in format_table(rows):
            print(line)

    def show_lifetime_stats(self, summaries: list[DeckSummary], source: str) -> None:
        """Print saved statistics for every deck.

        Args:
            summaries: One summary per deck.
            source: Where the statistics were read from (shown to the user).
        """
        if not summaries:
            print(f"No quiz history yet ({source}). Play a quiz first.")
            return
        rows = [["Deck", "Sessions", "Questions", "Correct", "Accuracy", "Most missed"]]
        for summary in summaries:
            most_missed = shorten(", ".join(summary.most_missed), MAX_CELL_WIDTH)
            rows.append(
                [
                    summary.name,
                    str(summary.sessions),
                    str(summary.questions),
                    str(summary.correct),
                    f"{summary.accuracy:.1f}%",
                    most_missed or "-",
                ]
            )
        print(self._paint("Lifetime Stats", Style.BRIGHT) + f" ({source})")
        lines = format_table(rows)
        print(self._paint(lines[0], Style.BRIGHT))
        for line in lines[1:]:
            print(line)

    def show_info(self, message: str) -> None:
        """Print a neutral message to standard output."""
        print(message)

    def show_warning(self, message: str) -> None:
        """Print a warning to standard error."""
        print(self._paint(f"Warning: {message}", Fore.YELLOW), file=sys.stderr)

    def show_error(self, message: str) -> None:
        """Print an error to standard error."""
        print(self._paint(f"Error: {message}", Fore.RED), file=sys.stderr)

    def _paint(self, text: str, color: str) -> str:
        """Wrap ``text`` in a color code if colors are enabled."""
        if not self._use_color:
            return text
        return f"{color}{text}{Style.RESET_ALL}"


class UIWarningHandler(logging.Handler):
    """Logging handler that shows warnings to the user through the UI.

    Modules such as ``data_loader`` only use ``logging``; this handler is how
    their warnings (e.g. duplicate cards) reach the console. ERROR records
    are skipped because the code that logs an error also reports it to the
    user, and showing it twice is confusing.
    """

    def __init__(self, ui: ConsoleUI) -> None:
        """Create a handler for WARNING records only.

        Args:
            ui: The UI that displays the warnings.
        """
        super().__init__(level=logging.WARNING)
        self.addFilter(lambda record: record.levelno < logging.ERROR)
        self._ui = ui

    def emit(self, record: logging.LogRecord) -> None:
        """Show one log record as a warning.

        Args:
            record: The log record to display.
        """
        self._ui.show_warning(record.getMessage())
