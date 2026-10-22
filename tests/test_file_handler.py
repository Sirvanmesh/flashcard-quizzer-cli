"""Tests for the low-level JSON reader (utils/file_handler.py)."""

from pathlib import Path

import pytest

from utils.file_handler import JSONFileError, read_json_file, write_json_file


def test_read_json_file_returns_parsed_value(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text('{"cards": [1, 2]}', encoding="utf-8")

    assert read_json_file(path) == {"cards": [1, 2]}


def test_read_json_file_accepts_string_path_and_uppercase_extension(
    tmp_path: Path,
) -> None:
    path = tmp_path / "DATA.JSON"
    path.write_text("[]", encoding="utf-8")

    assert read_json_file(str(path)) == []


def test_read_json_file_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + '["café"]'.encode("utf-8"))

    assert read_json_file(path) == ["café"]


def test_read_json_file_missing_file(tmp_path: Path) -> None:
    with pytest.raises(JSONFileError, match="File not found"):
        read_json_file(tmp_path / "missing.json")


def test_read_json_file_directory_is_rejected(tmp_path: Path) -> None:
    folder = tmp_path / "folder.json"
    folder.mkdir()

    with pytest.raises(JSONFileError, match="Not a file"):
        read_json_file(folder)


def test_read_json_file_wrong_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "deck.csv"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(JSONFileError, match="Expected a .json file"):
        read_json_file(path)


def test_read_json_file_too_large_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "big.json"
    path.write_text("[" + "1," * 50 + "1]", encoding="utf-8")

    with pytest.raises(JSONFileError, match="too large"):
        read_json_file(path, max_bytes=10)


def test_read_json_file_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "latin1.json"
    path.write_bytes(b'["caf\xe9"]')

    with pytest.raises(JSONFileError, match="not valid UTF-8"):
        read_json_file(path)


def test_read_json_file_invalid_json_reports_line_and_column(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('[\n  {"front": "a",}\n]', encoding="utf-8")

    with pytest.raises(JSONFileError, match="line 2, column 17"):
        read_json_file(path)


@pytest.mark.parametrize(
    "error, message",
    [
        (FileNotFoundError, "File not found"),
        (IsADirectoryError, "Not a file"),
        (PermissionError, "Permission denied"),
    ],
)
def test_read_json_file_os_errors_during_read_are_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: type[OSError],
    message: str,
) -> None:
    path = tmp_path / "deck.json"
    path.write_text("[]", encoding="utf-8")

    def fail(*args: object, **kwargs: object) -> str:
        raise error("simulated")

    monkeypatch.setattr(Path, "read_text", fail)

    with pytest.raises(JSONFileError, match=message):
        read_json_file(path)


def test_write_json_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    data = [{"front": "café", "back": "coffee"}]

    write_json_file(path, data)

    assert read_json_file(path) == data
    assert "café" in path.read_text(encoding="utf-8")  # not escaped as \u00e9
    assert not (tmp_path / "out.json.tmp").exists()


def test_write_json_file_replaces_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text("old", encoding="utf-8")

    write_json_file(path, {"new": True})

    assert read_json_file(path) == {"new": True}


def test_write_json_file_wrong_extension_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(JSONFileError, match="Expected a .json file"):
        write_json_file(tmp_path / "out.txt", [])


def test_write_json_file_unwritable_location(tmp_path: Path) -> None:
    target = tmp_path / "missing_folder" / "out.json"

    with pytest.raises(JSONFileError, match="Could not write"):
        write_json_file(target, [])
