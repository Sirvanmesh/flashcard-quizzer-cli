"""Safe reading and writing of JSON files.

This module knows nothing about flashcards. It turns every low-level
file or parsing problem into a single :class:`JSONFileError` with a
message that is safe to show to the user.
"""

import json
import os
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB is far more than any real deck needs.


class JSONFileError(Exception):
    """Raised when a JSON file cannot be read or parsed."""


def read_json_file(path: str | Path, max_bytes: int = MAX_FILE_BYTES) -> Any:
    """Read and parse a UTF-8 encoded JSON file.

    Args:
        path: Location of the file. Must exist, be a regular file and have
            a ``.json`` extension (any case).
        max_bytes: Largest file size accepted, to avoid loading huge files
            into memory by mistake.

    Returns:
        The parsed JSON value (usually a list or dict).

    Raises:
        JSONFileError: If the file is missing, is a directory, has the wrong
            extension, is too large, cannot be read or decoded, or does not
            contain valid JSON.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise JSONFileError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise JSONFileError(f"Not a file: {file_path}")
    if file_path.suffix.lower() != ".json":
        raise JSONFileError(f"Expected a .json file, got '{file_path.name}'")

    try:
        size = file_path.stat().st_size
        if size > max_bytes:
            raise JSONFileError(
                f"File is too large ({size} bytes, limit {max_bytes}): {file_path}"
            )
        # utf-8-sig also accepts files saved with a BOM (e.g. by Notepad).
        text = file_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise JSONFileError(f"File not found: {file_path}") from exc
    except IsADirectoryError as exc:
        raise JSONFileError(f"Not a file: {file_path}") from exc
    except PermissionError as exc:
        raise JSONFileError(f"Permission denied: {file_path}") from exc
    except UnicodeDecodeError as exc:
        raise JSONFileError(f"File is not valid UTF-8 text: {file_path}") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise JSONFileError(
            f"Invalid JSON in {file_path.name} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc


def write_json_file(path: str | Path, data: Any) -> None:
    """Write ``data`` as pretty-printed UTF-8 JSON, replacing the file atomically.

    The data is written to a temporary file next to the target and then
    moved into place, so an interrupted write never leaves a half-written
    file behind.

    Args:
        path: Destination file. Must have a ``.json`` extension and its
            folder must already exist.
        data: Any JSON-serializable value.

    Raises:
        JSONFileError: If the extension is wrong or the file cannot be written.
    """
    file_path = Path(path)
    if file_path.suffix.lower() != ".json":
        raise JSONFileError(f"Expected a .json file, got '{file_path.name}'")

    temp_path = file_path.with_name(file_path.name + ".tmp")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        temp_path.write_text(text, encoding="utf-8")
        os.replace(temp_path, file_path)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise JSONFileError(
            f"Could not write {file_path}: {exc.strerror or exc}"
        ) from exc
