"""
Feed normalizer tests (app/feed/normalizer.py).

Covers field aliases, optional-field honesty (missing -> None/empty, nothing
fabricated), price coercion, availability mapping, currency defaults, and the
canonical normalize_offer() annotation applied to every feed row.
"""

import pytest

from app.feed.normalizer import normalize_record


def _row(**overrides):
    row = {
        "title": "Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
        "sku": "S24-BLACK-128",
        "price": "\u20b962,999",
        "actual_price": "\u20b970,999",
        "availability": "in stock",
        "url": "https://acme.example.com/s24",
        "image": "https://acme.example.com/s24.jpg",
        "store": "Acme Store",
        "brand": "Samsung",
        "category": "Mobile Phones",
    }
    row.update(overrides)
    return row


def _normalized(**overrides):
    return normalize_record(_row(**overrides), source="acme")


# -- core mapping -------------------------------------------------------

def test_title_aliases():
    assert _normalized()["title"] == "Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)"
    assert normalize_record({"name": "Named Product", "price": "100"}, "acme")["title"] == "Named Product"
    assert normalize_record({"product_name": "Product Name", "price": "100"}, "acme")["title"] == "Product Name"


def test_no_title_returns_none():
    assert normalize_record({"price": "100"}, "acme") is None
    assert normalize_record({"title": "", "price": "100"}, "acme") is None
    assert normalize_record({"title": "   ", "price": "100"}, "acme") is None


def test_sku_becomes_product_id():
    assert _normalized()["product_id"] == "S24-BLACK-128"
    assert normalize_record({"title": "X", "product_id": "PID-9", "price": "1"}, "acme")["product_id"] == "PID-9"


def test_missing_sku_is_empty_not_invented():
    assert _normalized(sku=None)["product_id"] == ""


def test_price_aliases():
    for key in ("price", "discount_price", "current_price", "selling_price", "final_price"):
        offer = normalize_record({"title": "X", key: "5500", "store": "Acme"}, "acme")
        assert offer["price_value"] == 5500.0, key
        assert offer["price"] == 5500.0, key


def test_actual_price_becomes_original_price():
    assert _normalized()["original_price"] == 70999.0
    for key in ("original_price", "mrp", "list_price", "striked_price"):
        offer = normalize_record({"title": "X", "price": "100", key: "200"}, "acme")
        assert offer["original_price"] == 200.0, key
    assert _normalized(actual_price=None)["original_price"] is None


def test_price_coercion_and_positive_only():
    assert normalize_record({"title": "X", "price": "79,999"}, "acme")["price_value"] == 79999.0
    assert normalize_record({"title": "X", "price": "Rs. 7999"}, "acme")["price_value"] == 7999.0
    assert normalize_record({"title": "X", "price": "free"}, "acme")["price_value"] is None
    assert normalize_record({"title": "X", "price": 0}, "acme")["price_value"] is None
    assert normalize_record({"title": "X", "price": -5}, "acme")["price_value"] is None
    assert normalize_record({"title": "X", "price": True}, "acme")["price_value"] is None


def test_price_display_formatted():
    assert _normalized()["price_display"] == "\u20b962,999"
    offer = normalize_record({"title": "X", "price": "79999"}, "acme")
    assert offer["price_display"] == "\u20b979,999"


def test_availability_mapping():
    assert _normalized()["availability"] == "in_stock"
    assert _normalized(availability="out of stock")["availability"] == "out_of_stock"
    assert _normalized(availability=True)["availability"] == "in_stock"
    assert _normalized(availability=False)["availability"] == "out_of_stock"
    assert _normalized(availability="1")["availability"] == "in_stock"
    assert _normalized(availability="0")["availability"] == "out_of_stock"
    # a value normalize_offer() does not understand stays None (unknown)
    assert _normalized(availability="preorder")["availability"] is None
    assert _normalized(availability=None)["availability"] is None


def test_url_image_store_aliases():
    assert _normalized()["url"] == "https://acme.example.com/s24"
    assert _normalized()["image"] == "https://acme.example.com/s24.jpg"
    assert _normalized()["platform"] == "Acme Store"
    assert normalize_record({"title": "X", "price": "1", "merchant_name": "M"}, "acme")["platform"] == "M"
    assert normalize_record({"title": "X", "price": "1", "product_url": "https://u"}, "acme")["url"] == "https://u"
    assert normalize_record({"title": "X", "price": "1", "image_url": "https://i"}, "acme")["image"] == "https://i"


def test_missing_url_stays_empty_not_fabricated():
    assert _normalized(url=None)["url"] == ""


def test_store_defaults_to_source():
    offer = normalize_record({"title": "X", "price": "100"}, "acme")
    assert offer["platform"] == "acme"


def test_optional_fields_honest_when_missing():
    offer = normalize_record({"title": "X", "price": "100"}, "acme")
    assert offer["description"] is None
    assert offer["brand"] is None
    assert offer["category"] is None
    assert offer["shipping"] is None
    assert offer["coupon"] is None
    assert offer["original_price"] is None
    assert offer["availability"] is None


def test_optional_fields_preserved_when_stated():
    offer = _normalized(shipping="2-3 days", coupon="ACME10", description="Desc",
                        brand="Samsung", category="Mobile Phones")
    assert offer["shipping"] == "2-3 days"
    assert offer["coupon"] == "ACME10"
    assert offer["description"] == "Desc"
    assert offer["brand"] == "Samsung"
    assert offer["category"] == "Mobile Phones"


def test_currency_defaults_to_inr_and_respects_feed():
    assert _normalized()["currency"] == "INR"
    assert _normalized(currency="USD")["currency"] == "USD"
    assert _normalized(currency="usd")["currency"] == "USD"
    assert _normalized(currency="\u20b9")["currency"] == "INR"


def test_product_key_generated():
    offer = normalize_record({"title": "Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
                              "price": "1"}, "acme")
    # "galaxy" is a Samsung brand alias, so the model fingerprint is s24-128gb.
    assert offer["product_key"] == "samsung-s24-128gb"


# -- canonical annotation (normalize_offer) ------------------------------

def test_normalize_offer_annotation_applied():
    offer = _normalized()
    assert offer["marketplace"] == "Acme Store"
    assert offer["marketplace_product_id"] == "S24-BLACK-128"
    assert offer["price"] == 62999.0
    assert offer["original_price"] == 70999.0
    assert offer["product_url"] == "https://acme.example.com/s24"
    assert offer["image_url"] == "https://acme.example.com/s24.jpg"
    assert offer["availability"] == "in_stock"
    assert offer["currency"] == "INR"
    assert offer["source_kind"] == "feed"


def test_source_kind_feed_never_fabricates_availability():
    # unknown availability stays None through the canonical annotation
    offer = normalize_record({"title": "X", "price": "1", "availability": "maybe"}, "acme")
    assert offer["availability"] is None


def test_non_dict_row_returns_none():
    assert normalize_record(None, "acme") is None
    assert normalize_record("row", "acme") is None
    assert normalize_record(["x"], "acme") is None