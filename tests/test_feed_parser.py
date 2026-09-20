"""
Feed parser tests (app/feed/parser.py).

Covers JSON list/object/single-record input, CSV input, structural failure
discipline, and honest skipping of non-dict members / blank lines.
"""

import json

import pytest

from app.feed import parser


def _product(**overrides):
    row = {
        "title": "Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
        "price": "62999",
        "availability": "in stock",
    }
    row.update(overrides)
    return row


# -- JSON ---------------------------------------------------------------

def test_json_list_parses():
    payload = [_product(), _product(title="Apple iPhone 15", price="79999")]
    rows = parser.rows_from_json(payload)
    assert rows == [_product(), _product(title="Apple iPhone 15", price="79999")]


def test_json_string_list_parses():
    payload = json.dumps([_product()])
    assert parser.rows_from_json(payload) == [_product()]


def test_json_object_with_products_list_parses():
    payload = {"products": [_product(), _product(title="Apple iPhone 15")]}
    rows = parser.rows_from_json(payload)
    assert len(rows) == 2


def test_json_object_scans_common_keys():
    payload = {"items": [_product(), _product()]}
    assert len(parser.rows_from_json(payload)) == 2


def test_json_single_object_wraps_as_one_row():
    payload = {"title": "One Phone", "price": "49999"}
    assert parser.rows_from_json(payload) == [{"title": "One Phone", "price": "49999"}]


def test_json_skips_non_dict_members():
    payload = [_product(), ["not", "a", "row"], "nope", 42, _product()]
    assert len(parser.rows_from_json(payload)) == 2


def test_json_empty_product_list_returns_empty():
    assert parser.rows_from_json({"products": []}) == []


def test_malformed_json_raises():
    with pytest.raises(ValueError):
        parser.rows_from_json("{not valid json")


def test_structural_error_raises():
    with pytest.raises(ValueError):
        parser.rows_from_json(42)


def test_json_strips_surrounding_whitespace():
    payload = [{"title": "  Trimmed Phone  ", "price": "  9999  "}]
    assert parser.rows_from_json(payload) == [{"title": "Trimmed Phone", "price": "9999"}]


# -- CSV ----------------------------------------------------------------

def test_csv_parses_with_headers():
    text = "name,price,availability\nSamsung S24,62999,in stock\nApple iPhone 15,79999,out of stock\n"
    rows = parser.rows_from_csv(text)
    assert rows == [
        {"name": "Samsung S24", "price": "62999", "availability": "in stock"},
        {"name": "Apple iPhone 15", "price": "79999", "availability": "out of stock"},
    ]


def test_csv_skips_blank_lines():
    text = "name,price\n\nSamsung S24,62999\n,\nApple iPhone 15,79999\n\n"
    rows = parser.rows_from_csv(text)
    assert [r["name"] for r in rows] == ["Samsung S24", "Apple iPhone 15"]


def test_csv_empty_and_header_only_return_empty():
    assert parser.rows_from_csv("") == []
    assert parser.rows_from_csv("name,price\n") == []          # header only
    assert parser.rows_from_csv("name,price\n\n\n") == []


# -- read_feed_file -----------------------------------------------------

def test_read_feed_file_json_by_content(tmp_path):
    feed = tmp_path / "feed.dat"
    feed.write_text(json.dumps([_product()]), encoding="utf-8")
    rows = parser.read_feed_file(str(feed))
    assert rows == [_product()]


def test_read_feed_file_csv_by_extension(tmp_path):
    feed = tmp_path / "feed.csv"
    feed.write_text("name,price\nSamsung S24,62999\n", encoding="utf-8")
    rows = parser.read_feed_file(str(feed))
    assert rows == [{"name": "Samsung S24", "price": "62999"}]


def test_read_feed_file_handles_bom(tmp_path):
    feed = tmp_path / "feed.csv"
    feed.write_bytes(b"\xef\xbb\xbfname,price\nSamsung S24,62999\n")
    assert parser.read_feed_file(str(feed)) == [{"name": "Samsung S24", "price": "62999"}]