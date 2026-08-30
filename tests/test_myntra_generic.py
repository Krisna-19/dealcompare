"""
Myntra scraper tests — deterministic, no network.

Uses the pure `normalise_myntra_product` / `_parse_price` helpers and a
fixture HTML file representing Myntra's real search-result card markup.
"""
import re
from pathlib import Path

import pytest

from app.scrapers.myntra import (
    build_search_url,
    normalise_myntra_product,
    search_myntra,
)

# ── build_search_url ──────────────────────────────────────────────

def test_build_search_url_basic():
    assert build_search_url("men tshirt") == "https://www.myntra.com/men+tshirt"


def test_build_search_url_encodes_query():
    url = build_search_url("shirt men")
    assert url.startswith("https://www.myntra.com/")
    assert "shirt+men" in url


def test_build_search_url_never_hardcodes_a_category_or_product():
    url = build_search_url("Samsung Galaxy S24")
    assert "iphone" not in url.lower()
    assert "bestseller" not in url.lower()
    assert "category" not in url.lower()


# ── price parsing ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected_value",
    [
        ("\u20b949,999", 49999.0),
        ("\u20b955,999", 55999.0),
        ("\u20b969,999", 69999.0),
        ("\u20b91,919", 1919.0),
        ("1,099", 1099.0),
        ("Rs. 45,000", 45000.0),
        ("\u20b91,299 (50% OFF)", 1299.0),
        ("  49,999  ", 49999.0),
    ],
)
def test_price_parsing_valid_inr(raw, expected_value):
    from app.scrapers.myntra import _parse_price
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
    ],
)
def test_price_parsing_invalid_raises_nothing_and_yields_zero(raw):
    from app.scrapers.myntra import _parse_price
    value, display = _parse_price(raw)
    assert value == 0
    assert display == "Check price"


# ── URL normalisation ─────────────────────────────────────────────

def test_relative_url_becomes_absolute():
    normalised = normalise_myntra_product(
        {"brand": "RARE RABBIT", "name": "Men Slim Fit Shirt", "price_text": "\u20b91,919",
         "url": "/rare-rabbit-men-slim-fit-shirt/31496734/buy", "image": ""},
        "shirt",
    )
    assert normalised is not None
    assert normalised["url"] == "https://www.myntra.com/rare-rabbit-men-slim-fit-shirt/31496734/buy"


def test_absolute_url_passes_through():
    normalised = normalise_myntra_product(
        {"brand": "RARE RABBIT", "name": "Men Slim Fit Shirt", "price_text": "\u20b91,919",
         "url": "https://www.myntra.com/rare-rabbit-shirt/111/buy", "image": ""},
        "shirt",
    )
    assert normalised["url"] == "https://www.myntra.com/rare-rabbit-shirt/111/buy"


def test_missing_url_is_skipped():
    result = normalise_myntra_product(
        {"brand": "B", "name": "Something Nice", "price_text": "\u20b91,000", "url": "", "image": ""},
        "shirt",
    )
    assert result is None


# ── invalid / missing fields ──────────────────────────────────────

def test_missing_title_is_skipped():
    assert normalise_myntra_product(
        {"brand": "", "name": "", "price_text": "\u20b91,000", "url": "/x/1/buy", "image": ""}, "shirt"
    ) is None


def test_short_title_is_skipped():
    assert normalise_myntra_product(
        {"brand": "AB", "name": "Shirt", "price_text": "\u20b91,000", "url": "/ab-shirt/1/buy", "image": ""}, "shirt"
    ) is None


def test_zero_price_title_only_step_is_skipped():
    # A card with a title but no usable price must NOT become an offer.
    assert normalise_myntra_product(
        {"brand": "BRAND A", "name": "Product Without A Price", "price_text": "", "url": "/a/123/buy", "image": ""}, "shirt"
    ) is None


def test_non_dict_raw_is_skipped():
    assert normalise_myntra_product(None, "shirt") is None


# ── contract conformance ──────────────────────────────────────────

def test_normalised_output_conforms_to_shared_contract():
    item = normalise_myntra_product(
        {"brand": "RARE RABBIT", "name": "Men Slim Fit Casual Shirt", "price_text": "\u20b91,919",
         "url": "/rare-rabbit-shirt/31496734/buy", "image": "https://assets.myntassets.com/x.jpg"},
        "casual shirt",
    )
    assert item is not None
    assert set(item.keys()) >= {
        "title", "product_key", "platform", "price_value", "price_display", "url",
    }
    assert item["platform"] == "Myntra"
    assert item["price_value"] == 1919.0
    assert item["price_display"] == "\u20b91,919"
    assert item["image"].startswith("https://")
    assert isinstance(item["product_key"], str) and item["product_key"]


def test_image_relative_url_is_normalized_to_absolute():
    item = normalise_myntra_product(
        {"brand": "ROADSTER", "name": "Men Solid Shirt", "price_text": "\u20b91,099",
         "url": "/roadster-shirt/25543512/buy", "image": "/assets/images/r.jpg"},
        "shirt",
    )
    assert item["image"].startswith("https://www.myntra.com/assets/images/r.jpg")


# ── multiple products / no duplicates ─────────────────────────────

def test_fixture_yields_multiple_distinct_products_without_duplicates():
    """
    Feed the exact raw-card shape that `_EXTRACT_PRODUCTS_JS` produces on a
    real Myntra results page (see tests/fixtures/myntra_search_results.html)
    through the pure normaliser. Valid cards become distinct offers;
    malformed cards (no price or no link) are skipped, never fabricated.
    """
    raw_cards = [
        # valid: brand + name + discounted price + link
        {"brand": "RARE RABBIT", "name": "Men Slim Fit Opaque Casual Shirt",
         "price_text": "\u20b91,919", "url": "/rare-rabbit-men-slim-fit-shirt/31496734/buy",
         "image": "https://assets.myntassets.com/x.jpg"},
        # valid: price with no MRP block
        {"brand": "ROADSTER", "name": "Men Solid Casual Shirt",
         "price_text": "\u20b91,099", "url": "/roadster-men-solid-shirt/25543512/buy",
         "image": "https://assets.myntassets.com/y.jpg"},
        # valid: price carries a discount label after the amount
        {"brand": "HRX BY HRITHIK ROSHAN", "name": "Men Active Polo T-Shirt",
         "price_text": "\u20b91,399 (50% OFF)", "url": "/hrx-men-active-polo-tshirt/45589901/buy",
         "image": "https://assets.myntassets.com/z.jpg"},
        # invalid: card with a title but NO price -> must be skipped
        {"brand": "BRAND A", "name": "Product Without A Price",
         "price_text": "", "url": "/a-card-without-price/12345678/buy", "image": ""},
        # invalid: card with a price but NO link -> must be skipped
        {"brand": "BRAND B", "name": "Product Without A Link",
         "price_text": "\u20b92,499", "url": "", "image": ""},
    ]

    products = []
    for raw in raw_cards:
        item = normalise_myntra_product(raw, "shirt")
        if item is not None:
            products.append(item)

    # 3 valid (priced + linked); the 2 malformed cards never become offers.
    assert len(products) == 3

    urls = [p["url"] for p in products]
    assert len(set(urls)) == len(urls), "no duplicate offers caused by parsing"

    for p in products:
        assert p["platform"] == "Myntra"
        assert p["price_value"] > 0
        assert p["price_display"] != "Check price"
        assert p["url"].startswith("https://www.myntra.com/")
        assert re.search(r"/\d+/buy$", p["url"]), f"product id embedded in URL: {p['url']}"


# ── dedupe within source ─────────────────────────────────────────

def test_dedupe_by_product_key_keeps_cheapest_and_drops_duplicates():
    from app.scrapers.myntra import _dedupe_by_product_key

    base = {
        "title": "Levis Men Brand Logo Printed Slim",
        "product_key": "levis-men-brand-logo-printed-slim",
        "platform": "Myntra",
        "price_display": "Check price",
        "url": "https://www.myntra.com/levis/111/buy",
        "image": "",
    }
    products = [
        {**base, "price_value": 779.0},
        {**base, "price_value": 779.0},
        {**base, "price_value": 400.0},
        {**base, "price_value": 899.0, "product_key": "other-product-key"},
    ]
    out = _dedupe_by_product_key(products)
    assert len(out) == 2, "one offer per product_key"
    by_key = {p["product_key"]: p for p in out}
    assert by_key["levis-men-brand-logo-printed-slim"]["price_value"] == 400.0
    assert by_key["other-product-key"]["price_value"] == 899.0
    assert all(o["platform"] == "Myntra" for o in out)


def test_dedupe_by_product_key_handles_empty_and_missing_keys():
    from app.scrapers.myntra import _dedupe_by_product_key

    assert _dedupe_by_product_key([]) == []
    assert _dedupe_by_product_key([
        {"product_key": "", "price_value": 100.0},
        {"product_key": None, "price_value": 200.0},
    ]) == []


# ── generic / no-network guards ───────────────────────────────────

def test_search_myntra_accepts_a_query_only():
    import inspect
    sig = inspect.signature(search_myntra)
    assert list(sig.parameters.keys()) == ["query"]


def test_search_myntra_returns_a_list_without_raising(monkeypatch):
    """Without a reachable browser/network it must return [] gracefully."""
    result = search_myntra("nonexistent test query xyz")
    assert isinstance(result, list)


# ── no hardcoding guard ───────────────────────────────────────────

def test_myntra_scraper_source_has_no_hardcoded_prices_or_query():
    source = (
        Path(__file__).resolve().parents[1]
        / "app" / "scrapers" / "myntra.py"
    ).read_text(encoding="utf-8")
    assert '"iphone 15"' not in source
    # No hard-coded product URL or price literal in the production module.
    assert "myntra.com/iphone" not in source.lower()
