"""
Cross-marketplace offer contract tests (Phase G).

Every connector output carries the shared base contract PLUS the additive
canonical comparison field set produced by normalize_offer():
marketplace, marketplace_product_id, price, original_price, currency,
availability, product_url, image_url, product_key, captured_at, source_kind.

The canonical keys never replace or remove the base keys (title, product_key,
platform, price_value, price_display, url, image) the aggregator/catalog/
frontend read, and they never fabricate data: values are only filled in when a
source actually reports them.
"""
import json
import pathlib

from app.scrapers.contract import normalize_offer
from app.scrapers import amazon_creators
from app.scrapers.flipkart_api import _normalise_api_product
from app.scrapers.myntra import normalise_myntra_product


FIXTURES = pathlib.Path(__file__).parent / "fixtures"


CANONICAL_KEYS = {
    "marketplace",
    "marketplace_product_id",
    "price",
    "original_price",
    "currency",
    "availability",
    "product_url",
    "image_url",
    "product_key",
    "captured_at",
    "source_kind",
}

BASE_KEYS = {
    "title",
    "product_key",
    "platform",
    "price_value",
    "price_display",
    "url",
    "image",
}


# --- normalize_offer unit behaviour -----------------------------------------

def test_normalize_adds_canonical_keys_without_removing_base():
    offer = normalize_offer({
        "title": "Apple iPhone 15 (128 GB)",
        "product_key": "apple-iphone-15-128gb",
        "platform": "Amazon",
        "price_value": 74999.0,
        "price_display": "\u20b974,999",
        "url": "https://www.amazon.in/dp/B0ABC",
        "image": "https://img/iphone.jpg",
    }, source_kind="api")

    assert BASE_KEYS.issubset(set(offer.keys()))
    assert CANONICAL_KEYS.issubset(set(offer.keys()))
    assert offer["marketplace"] == "Amazon"
    assert offer["price"] == 74999.0
    assert offer["product_url"] == "https://www.amazon.in/dp/B0ABC"
    assert offer["image_url"] == "https://img/iphone.jpg"
    assert offer["currency"] == "INR"
    assert offer["availability"] is None  # never invented when unknown
    assert offer["original_price"] is None
    assert offer["marketplace_product_id"] == ""
    assert offer["source_kind"] == "api"
    assert isinstance(offer["captured_at"], float)


def test_normalize_never_mutates_the_input_dict():
    raw = {
        "title": "Samsung Galaxy S24 (128 GB)",
        "product_key": "samsung-s24-128gb",
        "platform": "Flipkart",
        "price_value": 54999.0,
        "price_display": "\u20b954,999",
        "url": "https://www.flipkart.com/p/itm",
        "image": "",
    }
    snapshot = dict(raw)

    normalize_offer(raw, source_kind="api")

    assert raw == snapshot, "normalize_offer must return a copy, never mutate"


def test_normalize_preserves_explicit_values_and_extras():
    offer = normalize_offer({
        "title": "x", "product_key": "x", "platform": "Myntra",
        "price_value": 1299.0, "price_display": "\u20b91,299",
        "url": "https://www.myntra.com/x/1/buy", "image": "",
        "product_id": "49429950",
        "original_price": 2999.0,
        "currency": "INR",
        "availability": "in_stock",
        "captured_at": 123456.0,
        "custom_field": "kept",
    })

    assert offer["marketplace_product_id"] == "49429950"
    assert offer["original_price"] == 2999.0
    assert offer["captured_at"] == 123456.0  # explicit captured_at wins
    assert offer["custom_field"] == "kept"   # unknown extras survive


def test_normalize_drops_non_positive_original_price():
    offer = normalize_offer({
        "title": "x", "product_key": "x", "platform": "Ajio",
        "price_value": 1299.0, "price_display": "\u20b91,299",
        "url": "https://www.ajio.com/x/p/1", "image": "",
        "original_price": 0,  # a zero MRP is not a real list price
    })
    assert offer["original_price"] is None


def test_normalize_drops_unknown_availability_types():
    offer = normalize_offer({
        "title": "x", "product_key": "x", "platform": "Ajio",
        "price_value": 1299.0, "price_display": "\u20b91,299",
        "url": "https://www.ajio.com/x/p/1", "image": "",
        "availability": "maybe-someday",
    })
    assert offer["availability"] is None


# --- Connector-level compliance ---------------------------------------------

def test_flipkart_api_offers_carry_canonical_contract():
    raw = json.loads(
        (FIXTURES / "flipkart_api_response.json").read_text(encoding="utf-8")
    )
    first = _normalise_api_product(raw["productInfoList"][0])

    assert first is not None
    assert CANONICAL_KEYS.issubset(set(first.keys()))
    assert first["marketplace"] == "Flipkart"
    assert first["marketplace_product_id"] == "MOBFHG3DGYYFNVQQ"
    assert first["product_id"] == "MOBFHG3DGYYFNVQQ"
    assert first["price"] == 59900.0
    assert first["original_price"] == 79900.0  # maximumRetailPrice above price
    assert first["availability"] == "in_stock"
    assert first["currency"] == "INR"
    assert first["source_kind"] == "api"
    assert first["url"] == first["product_url"]


def test_myntra_offer_carries_canonical_contract():
    offer = normalise_myntra_product(
        {
            "brand": "Farah",
            "name": "Slim Fit Chinos",
            "price_text": "\u20b91,299",
            "url": "/mens-chinos/farah/49429950/buy",
            "mrp": 2999.0,
            "product_id": "49429950",
        },
        "chinos",
        source_kind="http",
    )

    assert offer is not None
    assert CANONICAL_KEYS.issubset(set(offer.keys()))
    assert offer["marketplace"] == "Myntra"
    assert offer["marketplace_product_id"] == "49429950"
    assert offer["currency"] == "INR"
    assert offer["original_price"] == 2999.0
    assert offer["source_kind"] == "http"


def test_amazon_creators_offer_carries_canonical_contract():
    item = {
        "asin": "B0TEST0001",
        "detailPageURL": "https://www.amazon.in/dp/B0TEST0001",
        "images": {"primary": {"large": {"url": "https://media.amazon.in/a.jpg"}}},
        "itemInfo": {"title": {"displayValue": "Samsung Galaxy S24 5G (Onyx Black, 128 GB)"}},
        "offersV2": {"listings": [
            {
                "availability": {"type": "IN_STOCK", "message": "In Stock"},
                "price": {
                    "money": {"amount": 61999.0, "currency": "INR", "displayAmount": "₹61,999.00"},
                    "savingBasis": {"money": {"amount": 64999.0, "currency": "INR", "displayAmount": "₹64,999.00"}},
                },
            }
        ]},
    }

    offer = amazon_creators._extract_item(item)

    assert offer is not None
    assert CANONICAL_KEYS.issubset(set(offer.keys()))
    assert offer["marketplace"] == "Amazon"
    assert offer["marketplace_product_id"] == "B0TEST0001"
    assert offer["price"] == 61999.0
    assert offer["original_price"] == 64999.0
    assert offer["availability"] == "in_stock"
    assert offer["currency"] == "INR"
    assert offer["source_kind"] == "api"


def test_amazon_creators_offer_has_no_original_price_when_absent():
    item = {
        "asin": "B0TEST0002",
        "detailPageURL": "https://www.amazon.in/dp/B0TEST0002",
        "images": {"primary": {"large": {"url": "https://media.amazon.in/b.jpg"}}},
        "itemInfo": {"title": {"displayValue": "Apple iPhone 15 (Black, 128 GB)"}},
        "offersV2": {"listings": [
            {
                "availability": {"type": "IN_STOCK"},
                "price": {"money": {"amount": 69999.0, "currency": "INR", "displayAmount": "₹69,999.00"}},
            }
        ]},
    }

    offer = amazon_creators._extract_item(item)
    assert offer is not None
    assert offer["original_price"] is None
    assert offer["availability"] == "in_stock"