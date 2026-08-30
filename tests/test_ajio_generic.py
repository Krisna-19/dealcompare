"""
Ajio scraper tests — deterministic, no network.

Uses the pure `build_search_url` / `normalise_ajio_product` / `_parse_price`
helpers and raw records shaped like the DOM extractor's output.  Live Ajio is
behind an Akamai 403 block in this environment, so `search_ajio` is only
asserted for the honest-empty / no-raise contract here (never fabricated).
"""
import inspect
from pathlib import Path

import pytest

from app.scrapers.ajio import (
    _absolute_url,
    _dedupe_by_product_key,
    _parse_price,
    build_search_url,
    normalise_ajio_product,
    search_ajio,
)


# ── build_search_url ──────────────────────────────────────────────

def test_build_search_url_never_hardcodes_category_or_product():
    url = build_search_url("samsung galaxy s24")
    assert "/search/" in url
    assert "iphone" not in url.lower()
    assert "bestseller" not in url.lower()
    assert "category" not in url.lower()


def test_build_search_url_encodes_query():
    url = build_search_url("samsung galaxy s24")
    assert url.startswith("https://www.ajio.com/search/")
    # Original words survive; spaces become + (URL-safe) and are still
    # recognised as spaces by the path-based router.
    assert "samsung" in url
    assert "galaxy" in url
    assert "s24" in url


def test_build_search_url_encodes_special_characters():
    url = build_search_url("men's t-shirt 100%")
    assert url.startswith("https://www.ajio.com/search/")
    # No raw spaces or unsafe characters in the built URL.
    assert " " not in url


def test_build_search_url_basic():
    assert build_search_url("men tshirt") == "https://www.ajio.com/search/men+tshirt"


# ── price parsing ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected_value",
    [
        ("\u20b974,990", 74990.0),
        ("\u20b91,199", 1199.0),
        ("\u20b9124,990", 124990.0),
        ("Rs. 2,999", 2999.0),
        ("1,099", 1099.0),
        ("\u20b91,299 (50% OFF)", 1299.0),
        ("  49,999  ", 49999.0),
    ],
)
def test_price_parsing_valid_inr(raw, expected_value):
    value, display = _parse_price(raw)
    assert value == expected_value
    assert display == f"\u20b9{int(expected_value):,}"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        None,
        "Check price",
        "Out of stock",
        "\u20b90",
        "Free",
        "Sold Out",
    ],
)
def test_price_parsing_invalid_yields_zero(raw):
    value, display = _parse_price(raw)
    assert value == 0
    assert display == "Check price"


# ── URL normalisation ─────────────────────────────────────────────

def test_relative_url_becomes_absolute():
    assert _absolute_url("/samsung-galaxy-s24/440001006/buy") == (
        "https://www.ajio.com/samsung-galaxy-s24/440001006/buy"
    )


def test_absolute_url_passes_through():
    assert _absolute_url("https://www.ajio.com/p/440001006") == (
        "https://www.ajio.com/p/440001006"
    )


def test_missing_url_is_none():
    assert _absolute_url(None) is None
    assert _absolute_url("") is None


# ── normalise_ajio_product ────────────────────────────────────────

def test_valid_ajio_product_normalises_correctly():
    item = normalise_ajio_product(
        {
            "brand": "Samsung",
            "name": "Galaxy S24 5G Mobile (Onyx Black, 128 GB)",
            "price_text": "\u20b974,990",
            "url": "/samsung-galaxy-s24-5g-mobile/p/440001006",
            "image": "https://assets.ajio.com/img/s24.jpg",
        },
        "samsung galaxy s24",
    )
    assert item is not None
    assert set(item.keys()) >= {
        "title", "product_key", "platform", "price_value", "price_display", "url",
    }
    assert item["platform"] == "Ajio"
    assert item["price_value"] == 74990.0
    assert item["price_display"] == "\u20b974,990"
    assert item["url"].startswith("https://www.ajio.com/")
    assert item["image"].startswith("https://")


def test_valid_s24_plus_normalises_to_s24_plus_product_key():
    item = normalise_ajio_product(
        {
            "brand": "Samsung",
            "name": "Galaxy S24+ 5G (Onyx Black, 256 GB)",
            "price_text": "\u20b999,990",
            "url": "/samsung-galaxy-s24-plus-5g/p/440002000",
        },
        "samsung galaxy s24 plus",
    )
    assert item is not None
    assert item["product_key"] == "samsung-s24-plus-256gb"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        {"brand": "A", "name": "", "price_text": "\u20b91,000", "url": "/x/p"},
    ],
)
def test_short_or_missing_title_is_skipped(raw):
    assert normalise_ajio_product(raw, "shirt") is None


def test_missing_price_is_skipped():
    assert normalise_ajio_product(
        {"brand": "Brand", "name": "Samsung Galaxy S24 Smartphone",
         "price_text": "", "url": "/s24/p/1"}, "s24"
    ) is None


def test_zero_price_is_skipped():
    assert normalise_ajio_product(
        {"brand": "Brand", "name": "Samsung Galaxy S24 Smartphone",
         "price_text": "\u20b90", "url": "/s24/p/1"}, "s24"
    ) is None


def test_invalid_non_numeric_price_is_skipped():
    assert normalise_ajio_product(
        {"brand": "Brand", "name": "Samsung Galaxy S24 Smartphone",
         "price_text": "Check price", "url": "/s24/p/1"}, "s24"
    ) is None


def test_missing_url_is_skipped():
    assert normalise_ajio_product(
        {"brand": "Brand", "name": "Samsung Galaxy S24 Smartphone",
         "price_text": "\u20b974,990", "url": ""}, "s24"
    ) is None


def test_image_relative_url_is_normalized_to_absolute():
    item = normalise_ajio_product(
        {"brand": "Samsung", "name": "Galaxy S24 5G (Onyx Black, 128 GB)",
         "price_text": "\u20b974,990", "url": "/s24/p/1",
         "image": "/img/s24.jpg"},
        "samsung galaxy s24",
    )
    assert item["image"] == "https://www.ajio.com/img/s24.jpg"


def test_non_dict_raw_is_skipped():
    assert normalise_ajio_product(None, "s24") is None


# ── fixture-driven extraction (raw records shaped like the DOM JS) ─

def test_fixture_yields_distinct_products_without_duplicates():
    """
    Feed the exact raw-record shape that `_EXTRACT_PRODUCTS_JS` produces on a
    real Ajio results page through the pure normaliser.  Valid cards become
    distinct offers; malformed cards (no price / no link) never become offers.
    """
    raw_cards = [
        {
            "brand": "Samsung",
            "name": "Galaxy S24 5G Mobile (Onyx Black, 128 GB)",
            "price_text": "\u20b974,990",
            "url": "/samsung-galaxy-s24-5g/p/440001006",
            "image": "https://assets.ajio.com/img/s24.jpg",
        },
        {
            "brand": "CaseMate",
            "name": "Samsung Galaxy S24 Back Case Compatible",
            "price_text": "\u20b91,199",
            "url": "/casemate-s24-back-case/p/440002011",
            "image": "",
        },
        {
            "brand": "Samsung",
            "name": "Galaxy S24 Ultra 5G (Titanium Black, 256 GB)",
            "price_text": "\u20b9124,990",
            "url": "/samsung-galaxy-s24-ultra/p/440003020",
            "image": "https://assets.ajio.com/img/ultra.jpg",
        },
        # malformed: no usable price
        {
            "brand": "Brand A",
            "name": "Product Without A Price",
            "price_text": "Check price",
            "url": "/brand-a/p/1",
            "image": "",
        },
        # malformed: no link (should never become an offer)
        {
            "brand": "Brand B",
            "name": "Product Without A Link",
            "price_text": "\u20b92,999",
            "url": "",
            "image": "",
        },
    ]

    products = []
    for raw in raw_cards:
        item = normalise_ajio_product(raw, "samsung galaxy s24")
        if item is not None:
            products.append(item)

    # All 3 priced + linked cards become valid offers at the SCRAPER level
    # (the per-source fuzzy gate is intentionally coarse, matching every other
    # scraper).  Sub-variant relevance (e.g. keeping the base S24 and its case
    # but separating the S24 Ultra) is enforced downstream by
    # filter_irrelevant_products, not inside the scraper normaliser.
    assert len(products) == 3
    urls = [p["url"] for p in products]
    assert len(set(urls)) == len(urls), "no duplicate offers"
    for p in products:
        assert p["platform"] == "Ajio"
        assert p["price_value"] > 0
        assert p["price_display"] != "Check price"
        assert p["url"].startswith("https://www.ajio.com/")


# ── match-score behaviour ─────────────────────────────────────────

def test_match_score_gate_follows_shared_scraper_convention():
    """
    The per-source normaliser applies the same fuzzy `match_score_threshold`
    gate as the Amazon/Flipkart/Myntra scrapers.  That gate is intentionally
    coarse (a short fashion title can pass a phone query); the strict variant
    identity/relevance enforcement is done downstream in
    filter_irrelevant_products (covered by tests/test_filter_relevance.py).
    This test locks the consistent convention: an on-topic title passes and
    yields a real Ajio offer, never fabricated data.
    """
    item = normalise_ajio_product(
        {"brand": "Samsung", "name": "Galaxy S24 5G Mobile (Onyx Black, 128 GB)",
         "price_text": "\u20b974,990", "url": "/samsung-galaxy-s24-5g/p/440001006"},
        "samsung galaxy s24",
    )
    assert item is not None
    assert item["platform"] == "Ajio"
    assert item["price_value"] > 0
    assert item["url"].startswith("https://www.ajio.com/")


# ── dedupe / cap helpers ──────────────────────────────────────────

def test_dedupe_by_product_key_keeps_cheapest_and_drops_duplicates():
    base = {
        "title": "Samsung Galaxy S24 (Onyx Black, 128 GB)",
        "product_key": "samsung-s24-128gb",
        "platform": "Ajio",
        "price_display": "\u20b974,990",
        "url": "https://www.ajio.com/samsung-galaxy-s24/p/440001006",
        "image": "",
    }
    products = [
        {**base, "price_value": 75990.0},
        {**base, "price_value": 75990.0},
        {**base, "price_value": 74990.0},
        {**base, "price_value": 80000.0, "product_key": "other-key"},
    ]
    out = _dedupe_by_product_key(products)
    assert len(out) == 2, "one offer per product_key"
    by_key = {p["product_key"]: p for p in out}
    assert by_key["samsung-s24-128gb"]["price_value"] == 74990.0
    assert all(o["platform"] == "Ajio" for o in out)


def test_dedupe_by_product_key_handles_empty_and_missing_keys():
    assert _dedupe_by_product_key([]) == []
    assert _dedupe_by_product_key([
        {"product_key": "", "price_value": 100.0},
        {"product_key": None, "price_value": 200.0},
    ]) == []


# ── generic / no-network guards ───────────────────────────────────

def test_search_ajio_accepts_a_query_only():
    sig = inspect.signature(search_ajio)
    assert list(sig.parameters.keys()) == ["query"]


def test_search_ajio_returns_a_list_without_raising():
    """Without a reachable Ajio it must return [] gracefully (honest empty)."""
    result = search_ajio("nonexistent test query xyz")
    assert isinstance(result, list)
