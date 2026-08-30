"""
Deterministic Flipkart extraction tests using saved fixtures.
No network access — parses __NEXT_DATA__ JSON directly.
"""

import json
import pathlib

from app.scrapers.flipkart import _normalise_next_data_product

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
NEXT_DATA_FILE = FIXTURES / "flipkart_next_data.json"


def _load_next_data():
    with open(NEXT_DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _get_all_products(data):
    """Walk the fixture's card tree and return the raw product list."""
    products = []
    cards = (
        data.get("props", {})
        .get("pageProps", {})
        .get("initialData", {})
        .get("data", {})
        .get("cards", [])
    )
    for card in cards:
        widget_data = card.get("card", {}).get("widget", {}).get("data", {})
        for p in widget_data.get("products", []):
            products.append(p)
    return products


# --- Normalisation tests ---------------------------------------------------

def test_normalise_first_product():
    data = _load_next_data()
    raw = _get_all_products(data)[0]
    result = _normalise_next_data_product(raw)

    assert result is not None
    assert result["platform"] == "Flipkart"
    assert result["title"] == "Apple iPhone 15 (Black, 128 GB)"
    assert result["price_value"] == 59900
    assert result["price_display"] == "₹59,900"
    assert "MOBGCNQFKY6YJPZQ" in result["url"]
    assert result["image"].startswith("https://")


def test_normalise_second_product():
    data = _load_next_data()
    raw = _get_all_products(data)[1]
    result = _normalise_next_data_product(raw)

    assert result["title"] == "Apple iPhone 15 (Blue, 128 GB)"
    assert result["price_value"] == 59900
    assert result["platform"] == "Flipkart"


def test_normalise_third_product():
    data = _load_next_data()
    raw = _get_all_products(data)[2]
    result = _normalise_next_data_product(raw)

    assert result["title"] == "Samsung Galaxy S24 5G (Onyx Black, 128 GB)"
    assert result["price_value"] == 64999
    assert result["price_display"] == "₹64,999"


def test_all_products_have_product_key():
    data = _load_next_data()
    for raw in _get_all_products(data):
        result = _normalise_next_data_product(raw)
        assert result is not None
        assert result["product_key"], "product_key must not be empty"
        assert isinstance(result["product_key"], str)
        assert len(result["product_key"]) > 0


def test_all_products_have_valid_url():
    data = _load_next_data()
    for raw in _get_all_products(data):
        result = _normalise_next_data_product(raw)
        assert result is not None
        assert result["url"].startswith("https://www.flipkart.com/")


def test_product_key_matches_title():
    from app.utils.text_utils import generate_product_key

    data = _load_next_data()
    for raw in _get_all_products(data):
        result = _normalise_next_data_product(raw)
        assert result is not None
        expected_key = generate_product_key(result["title"])
        assert result["product_key"] == expected_key


def test_normalise_empty_dict_returns_none():
    assert _normalise_next_data_product({}) is None


def test_normalise_missing_title_returns_none():
    assert _normalise_next_data_product({"pricing": {"sellingPrice": 100}}) is None


def test_normalise_missing_url_returns_none():
    raw = {"productBrand": "Test Product", "pricing": {"sellingPrice": 100}}
    assert _normalise_next_data_product(raw) is None


def test_price_string_fallback():
    """If price arrives as a string with rupee symbol, it still parses."""
    raw = {
        "productBrand": "Shirt",
        "productUrl": "/shirt/p/123",
        "pricing": {"sellingPrice": "₹1,299"},
    }
    result = _normalise_next_data_product(raw)
    assert result is not None
    assert result["price_value"] == 1299


def test_zero_price_returns_check_price():
    raw = {
        "productBrand": "Free Item",
        "productUrl": "/item/p/456",
        "pricing": {"sellingPrice": 0},
    }
    result = _normalise_next_data_product(raw)
    assert result is not None
    assert result["price_display"] == "Check price"
    assert result["price_value"] == 0
