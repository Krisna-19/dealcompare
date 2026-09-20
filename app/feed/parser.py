"""Generic, marketplace-agnostic feed row reader for merchant product feeds.

Handles JSON and CSV input using only the standard library, returning a list of
plain dicts.  Rows that are not dicts and fully-empty CSV lines are skipped
honestly (the caller sees fewer rows than lines and can report that).
Structural problems in the feed itself raise a ValueError so the caller never
silently ingests a broken feed.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable

#: Common keys under which a JSON feed stores its list of products.
DICT_LIST_KEYS: tuple[str, ...] = ("products", "items", "rows", "records", "data")


def read_feed_file(path: str | Path) -> list[dict[str, Any]]:
    """Read a feed file, auto-detecting CSV vs JSON from the file extension.

    Args:
        path: Path to a ``.csv`` or ``.json`` feed file.

    Returns:
        A list of plain dict rows (never ``None`` members).

    Raises:
        ValueError: If the payload is structurally invalid.
        OSError: If the file cannot be read or decoded.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    if p.suffix.lower() == ".csv":
        return rows_from_csv(text)
    return rows_from_json(text)


def rows_from_text(text: str, text_format: str | None = None) -> list[dict[str, Any]]:
    """Parse feed text, using ``text_format`` (``"csv"``/``"json"``) when given,
    otherwise sniffing on the first non-whitespace character."""
    if text_format is not None:
        fmt = text_format.lower()
    else:
        stripped = text.lstrip()
        fmt = "csv" if stripped.startswith(",") or _looks_like_csv(stripped) else "json"
    if fmt == "csv":
        return rows_from_csv(text)
    return rows_from_json(text)


def rows_from_json(payload: str | bytes | dict | list) -> list[dict[str, Any]]:
    """Parse a JSON feed into a list of dict rows.

    Accepts either deserialized data or a JSON string.  A top-level list is
    treated as the rows; a top-level dict is scanned for a list under a common
    product key (``products``/``items``/``rows``/``records``/``data``) and, if
    none is found, treated as a single record.
    """
    if isinstance(payload, (str, bytes)):
        data = json.loads(payload)
    else:
        data = payload

    if isinstance(data, dict):
        for key in DICT_LIST_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return _clean_rows(value)
        return _clean_rows([data])
    if isinstance(data, list):
        return _clean_rows(data)
    raise ValueError(
        "JSON feed must be a list of objects or an object holding a "
        'list under one of: ' + ", ".join(DICT_LIST_KEYS)
    )


def rows_from_csv(text: str) -> list[dict[str, Any]]:
    """Parse a CSV feed into a list of dict rows.

    Fully-empty lines and rows with no usable values are skipped; rows that are
    present but malformed (wrong column count for a given header) are included
    with the cells that exist so the normalizer can later reject them
    honestly.
    """
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        if raw is None:
            continue
        kept = {k: v for k, v in raw.items() if k is not None}
        if not _has_values(kept):
            continue
        rows.append(_clean_row(kept))
    return rows


def _looks_like_csv(text: str) -> bool:
    sample = text.splitlines()
    if not sample:
        return False
    header = next((line for line in sample if line.strip()), "")
    return "," in header and header.count(",") >= 1


def _clean_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(_clean_row(row))
    return out


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (_strip_value(v)) for k, v in row.items()}


def _strip_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _has_values(row: dict[str, Any]) -> bool:
    return any(str(v).strip() for v in row.values())