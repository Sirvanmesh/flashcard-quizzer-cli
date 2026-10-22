"""Tests for loading and validating flashcard decks (data_loader.py)."""

import logging
from pathlib import Path
from typing import Any, Callable

import pytest

from data_loader import FlashcardLoadError, load_flashcards
from models import Flashcard

WriteJson = Callable[..., Path]


def test_load_valid_flashcards_array(write_json: WriteJson) -> None:
    path = write_json([{"front": "API", "back": "Application Programming Interface"}])

    cards = load_flashcards(path)

    assert cards == [Flashcard("API", "Application Programming Interface")]


def test_load_valid_flashcards_object(write_json: WriteJson) -> None:
    path = write_json(
        {"cards": [{"front": "def", "back": "keyword"}, {"front": "a", "back": "b"}]}
    )

    cards = load_flashcards(path)

    assert [card.front for card in cards] == ["def", "a"]


def test_load_invalid_json(write_text: Callable[..., Path]) -> None:
    path = write_text('[{"front": "API", "back": }]')

    with pytest.raises(FlashcardLoadError, match=r"Invalid JSON .* line 1, column"):
        load_flashcards(path)


def test_load_missing_required_field(write_json: WriteJson) -> None:
    path = write_json([{"front": "API"}])

    expected = 'Card 1: missing required field "back"'
    with pytest.raises(FlashcardLoadError, match=expected):
        load_flashcards(path)


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FlashcardLoadError, match="File not found"):
        load_flashcards(tmp_path / "does_not_exist.json")


@pytest.mark.parametrize("data", [[], {"cards": []}])
def test_load_empty_deck(write_json: WriteJson, data: Any) -> None:
    path = write_json(data)

    with pytest.raises(FlashcardLoadError, match="empty"):
        load_flashcards(path)


@pytest.mark.parametrize("data", ["just a string", 42, None, True])
def test_load_wrong_top_level_type(write_json: WriteJson, data: Any) -> None:
    path = write_json(data)

    with pytest.raises(FlashcardLoadError, match="must be a list of cards"):
        load_flashcards(path)


@pytest.mark.parametrize(
    "card, field",
    [({"front": "   ", "back": "x"}, "front"), ({"front": "x", "back": ""}, "back")],
)
def test_load_blank_values(
    write_json: WriteJson, card: dict[str, str], field: str
) -> None:
    path = write_json([card])

    with pytest.raises(FlashcardLoadError, match=f'Card 1: field "{field}" is blank'):
        load_flashcards(path)


def test_load_object_without_cards_key_is_rejected(write_json: WriteJson) -> None:
    path = write_json({"deck": []})

    with pytest.raises(FlashcardLoadError, match='missing the "cards" key'):
        load_flashcards(path)


def test_load_object_with_non_list_cards_is_rejected(write_json: WriteJson) -> None:
    path = write_json({"cards": {"front": "a", "back": "b"}})

    with pytest.raises(FlashcardLoadError, match='"cards" must be a list'):
        load_flashcards(path)


def test_load_non_dict_card_names_card_number(write_json: WriteJson) -> None:
    path = write_json([{"front": "a", "back": "b"}, ["not", "a", "dict"]])

    with pytest.raises(FlashcardLoadError, match="Card 2: expected an object"):
        load_flashcards(path)


def test_load_non_string_value_is_rejected(write_json: WriteJson) -> None:
    path = write_json([{"front": "a", "back": "b"}, {"front": 7, "back": "seven"}])

    with pytest.raises(FlashcardLoadError, match='Card 2: field "front" must be a str'):
        load_flashcards(path)


def test_load_strips_whitespace_from_values(write_json: WriteJson) -> None:
    path = write_json([{"front": "  API \n", "back": "\tInterface  "}])

    assert load_flashcards(path) == [Flashcard("API", "Interface")]


def test_load_ignores_extra_fields(write_json: WriteJson) -> None:
    path = write_json([{"front": "a", "back": "b", "hint": "ignored"}])

    assert load_flashcards(path) == [Flashcard("a", "b")]


def test_load_duplicate_fronts_warns_but_loads(
    write_json: WriteJson, caplog: pytest.LogCaptureFixture
) -> None:
    path = write_json(
        [
            {"front": "API", "back": "one"},
            {"front": "CPU", "back": "two"},
            {"front": "api", "back": "three"},
        ]
    )

    with caplog.at_level(logging.WARNING):
        cards = load_flashcards(path)

    assert len(cards) == 3
    assert 'Duplicate card front "api" (cards 1 and 3)' in caplog.text


def test_load_non_json_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "deck.txt"
    path.write_text('[{"front": "a", "back": "b"}]', encoding="utf-8")

    with pytest.raises(FlashcardLoadError, match="Expected a .json file"):
        load_flashcards(path)


@pytest.mark.parametrize(
    "name, count", [("glossary.json", 10), ("python_basics.json", 8)]
)
def test_load_bundled_sample_decks(data_dir: Path, name: str, count: int) -> None:
    cards = load_flashcards(data_dir / name)

    assert len(cards) == count
    assert all(card.front and card.back for card in cards)
