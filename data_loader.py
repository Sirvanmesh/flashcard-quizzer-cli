"""Load and validate flashcard decks from JSON files.

Two formats are supported::

    [{"front": "API", "back": "Application Programming Interface"}]
    {"cards": [{"front": "API", "back": "Application Programming Interface"}]}
"""

import logging
from pathlib import Path
from typing import Any

from models import Flashcard
from utils.file_handler import JSONFileError, read_json_file

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("front", "back")


class FlashcardLoadError(Exception):
    """Raised when a deck cannot be loaded or fails validation."""


def load_flashcards(path: str | Path) -> list[Flashcard]:
    """Load a deck of flashcards from a JSON file.

    Values are stripped of surrounding whitespace. Duplicate fronts are
    logged as a warning but do not stop the deck from loading.

    Args:
        path: Path to a ``.json`` deck in array or object format.

    Returns:
        The validated flashcards in file order.

    Raises:
        FlashcardLoadError: If the file cannot be read or the deck is invalid.
            The message names the 1-based card number when a card is at fault.
    """
    try:
        data = read_json_file(path)
    except JSONFileError as exc:
        raise FlashcardLoadError(str(exc)) from exc

    raw_cards = _extract_cards(data)
    if not raw_cards:
        raise FlashcardLoadError("The deck is empty: add at least one card.")

    cards = [_parse_card(raw, number) for number, raw in enumerate(raw_cards, 1)]
    _warn_about_duplicates(cards)
    return cards


def _extract_cards(data: Any) -> list[Any]:
    """Return the list of raw card entries from either supported format.

    Args:
        data: The parsed JSON document.

    Returns:
        The raw (unvalidated) card entries.

    Raises:
        FlashcardLoadError: If the document is neither a list nor an object
            with a ``"cards"`` list.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "cards" not in data:
            raise FlashcardLoadError(
                'The deck object is missing the "cards" key: '
                'expected {"cards": [...]}.'
            )
        cards = data["cards"]
        if not isinstance(cards, list):
            raise FlashcardLoadError(
                f'"cards" must be a list, got {type(cards).__name__}.'
            )
        return cards
    raise FlashcardLoadError(
        'The deck must be a list of cards or an object with a "cards" list, '
        f"got {type(data).__name__}."
    )


def _parse_card(raw: Any, number: int) -> Flashcard:
    """Validate one raw card entry and convert it to a :class:`Flashcard`.

    Args:
        raw: The raw JSON value for this card.
        number: The card's 1-based position, used in error messages.

    Returns:
        The validated card with whitespace stripped from both sides.

    Raises:
        FlashcardLoadError: If the entry is not an object or a required field
            is missing, not a string, or blank.
    """
    if not isinstance(raw, dict):
        raise FlashcardLoadError(
            f'Card {number}: expected an object with "front" and "back", '
            f"got {type(raw).__name__}."
        )

    values: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        if field not in raw:
            raise FlashcardLoadError(
                f'Card {number}: missing required field "{field}".'
            )
        value = raw[field]
        if not isinstance(value, str):
            raise FlashcardLoadError(
                f'Card {number}: field "{field}" must be a string, '
                f"got {type(value).__name__}."
            )
        stripped = value.strip()
        if not stripped:
            raise FlashcardLoadError(f'Card {number}: field "{field}" is blank.')
        values[field] = stripped

    return Flashcard(front=values["front"], back=values["back"])


def _warn_about_duplicates(cards: list[Flashcard]) -> None:
    """Log a warning for each front that appears more than once.

    Fronts are compared case-insensitively.

    Args:
        cards: The validated cards in file order.
    """
    first_seen: dict[str, int] = {}
    for number, card in enumerate(cards, 1):
        key = card.front.casefold()
        if key in first_seen:
            logger.warning(
                'Duplicate card front "%s" (cards %d and %d).',
                card.front,
                first_seen[key],
                number,
            )
        else:
            first_seen[key] = number
