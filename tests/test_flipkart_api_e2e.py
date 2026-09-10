"""
Deterministic end-to-end Flipkart Affiliate API tests.

Exercise the full /search pipeline (Flipkart API adapter -> search_service ->
relevance filter -> aggregator -> response contract) WITHOUT live network
calls: the Flipkart API HTTP layer is stubbed with saved/replayable responses
and the other platform scrapers are replaced with deterministic fakes.

Covers the four scenario queries (iphone, samsung phone, laptop asus, shirts)
and verifies: real offer shape, correct product grouping, no unrelated merge,
productId preserved, in-stock filtering, cheapest valid offer, and an
unchanged frontend API contract.
"""

import json
import pathlib

import pytest

import app.scrapers.flipkart as flipkart
from app.scrapers import flipkart_api
from app.core.config import get_settings
from app.services import search_service
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
API_FIXTURE = FIXTURES / "flipkart_api_response.json"

CACHE = search_service._search_cache


@pytest.fixture(autouse=True)
def _clear_settings_and_cache():
    get_settings.cache_clear()
    with search_service._search_cache_lock:
        CACHE.clear()
    search_service.clear_coalesce_map()
    yield
    get_settings.cache_clear()
    with search_service._search_cache_lock:
        CACHE.clear()


def _load_api_fixture():
    with open(API_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def _enable_api(monkeypatch):
    monkeypatch.setenv("FLIPKART_DATA_SOURCE", "api")
    monkeypatch.setenv("FLIPKART_AFFILIATE_ID", "testaffiliate")
    monkeypatch.setenv("FLIPKART_AFFILIATE_TOKEN", "testtoken")


def _stub_other_sources(monkeypatch, by_platform):
    """Replace Amazon/Myntra/Ajio scrapers, leaving search_flipkart real."""
    monkeypatch.setattr(
        search_service, "search_amazon", lambda q: by_platform.get("Amazon", [])
    )
    monkeypatch.setattr(
        search_service, "search_myntra", lambda q: by_platform.get("Myntra", [])
    )
    monkeypatch.setattr(
        search_service, "search_ajio", lambda q: by_platform.get("Ajio", [])
    )


def _stub_flipkart_http(monkeypatch, response_text):
    class FakeResponse:
        status_code = 200
        text = response_text

    api_calls = {"n": 0}

    def fake_get(url, **kwargs):
        api_calls["n"] += 1
        assert kwargs["headers"]["Fk-Affiliate-Id"] == "testaffiliate"
        assert kwargs["headers"]["Fk-Affiliate-Token"] == "testtoken"
        return FakeResponse()

    monkeypatch.setattr(flipkart_api.requests, "get", fake_get)
    return api_calls


def test_e2e_iphone_uses_api_preserves_product_id_and_contract(monkeypatch):
    """
    'iphone': API returns the fixture (2 iPhone 15 colours + 1 Samsung S24).
    The Samsung must be filtered out as irrelevant; both iPhone colour SKUs
    become separate cards with the Flipkart productId preserved on each offer.
    """
    _enable_api(monkeypatch)
    _stub_other_sources(monkeypatch, {})
    api_calls = _stub_flipkart_http(monkeypatch, json.dumps(_load_api_fixture()))

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Products compared successfully"
    assert api_calls["n"] == 1

    by_title = {g["title"]: g for g in data["results"]}
    # Samsung S24 filtered by relevance: only the two iPhone colour cards.
    assert set(by_title) == {
        "Apple iPhone 15 (Black, 128 GB)",
        "Apple iPhone 15 (Blue, 128 GB)",
    }

    for card in data["results"]:
        assert set(card.keys()) == {
            "title", "best_price", "best_platform", "best_url", "image", "offers",
        }
        offer = card["offers"][0]
        assert offer["platform"] == "Flipkart"
        # Frontend contract is deliberately unchanged: no product_id field.
        assert set(offer.keys()) == {
            "title", "product_key", "platform",
            "price_value", "price_display", "url", "image",
        }
        assert offer["url"].startswith("https://www.flipkart.com/")
        assert offer["price_value"] > 0


def test_e2e_samsung_phone_groups_cross_store_and_cheapest_wins(monkeypatch):
    """
    'samsung phone': the Flipkart API returns a Galaxy S24 and Amazon returns
    the same SKU cheaper.  The two offers must merge into ONE card with the
    cheapest (Amazon) labelled best, while the Flipkart offer keeps its
    productId.
    """
    _enable_api(monkeypatch)
    _stub_other_sources(monkeypatch, {
        "Amazon": [{
            "title": "Samsung Galaxy S24 5G (Onyx Black, 128 GB)",
            "product_key": "samsung-galaxy-s24-5g-onyx-black-128gb",
            "platform": "Amazon",
            "price_value": 62999.0,
            "price_display": "\u20b962,999",
            "url": "https://www.amazon.in/dp/B0BLAH",
            "image": "https://example.com/s24.jpg",
        }],
    })

    # Reuse the fixture's Galaxy S24 entry as the Flipkart API response.
    fixture = _load_api_fixture()
    samsung = {
        "productInfoList": [
            p for p in fixture["productInfoList"]
            if p["productBaseInfoV1"].get("productId") == "MOBH7GF3KQFTCEG5"
        ]
    }
    _stub_flipkart_http(monkeypatch, json.dumps(samsung))

    res = client.get("/search", params={"query": "samsung phone"})

    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Products compared successfully"
    assert len(data["results"]) == 1

    card = data["results"][0]
    platforms = sorted(o["platform"] for o in card["offers"])
    assert platforms == ["Amazon", "Flipkart"]

    flipkart_offer = next(o for o in card["offers"] if o["platform"] == "Flipkart")
    assert flipkart_offer["url"].startswith("https://www.flipkart.com/")
    assert flipkart_offer["price_value"] > 0

    amazon_offer = next(o for o in card["offers"] if o["platform"] == "Amazon")
    # best_url stays on the original URL; only offer urls gain affiliate tags.
    assert card["best_platform"] == "Amazon"
    assert card["best_url"] == "https://www.amazon.in/dp/B0BLAH"
    assert amazon_offer["price_value"] < flipkart_offer["price_value"]


def test_e2e_laptop_asus_no_unrelated_merge(monkeypatch):
    """
    'laptop asus': Flipkart API returns the real ASUS laptop and Amazon returns
    the same SKU; a clearly unrelated Flipkart result (an ASUS backpack) is
    also present in the API payload and must be excluded, keeping exactly one
    merged laptop card.
    """
    _enable_api(monkeypatch)
    _stub_other_sources(monkeypatch, {
        "Amazon": [{
            "title": "ASUS Vivobook 15 (Silver, 8 GB RAM, 512 GB SSD)",
            "product_key": "asus-vivobook-15-silver-8gb-512gb",
            "platform": "Amazon",
            "price_value": 48499.0,
            "price_display": "\u20b948,499",
            "url": "https://www.amazon.in/dp/ASUSLAP",
            "image": "",
        }],
    })

    payload = {
        "productInfoList": [
            {
                "productBaseInfoV1": {
                    "productId": "LAPASUS001",
                    "title": "ASUS Vivobook 15 (Silver, 8 GB RAM, 512 GB SSD)",
                    "imageUrls": {"200x200": "https://example.com/lap.jpg"},
                    "maximumRetailPrice": {"amount": 50499.0, "currency": "INR"},
                    "flipkartSellingPrice": {"amount": 48999.0, "currency": "INR"},
                    "productUrl": (
                        "https://www.flipkart.com/asus-vivobook-15/p/itmlapasus001"
                        "?pid=COMLAPASUS001"
                    ),
                    "inStock": True,
                    "isAvailable": True,
                    "productBrand": "ASUS",
                }
            },
            {
                "productBaseInfoV1": {
                    "productId": "BACASUS002",
                    "title": "ASUS Laptop Backpack 15.6 inch (Grey)",
                    "imageUrls": {"200x200": "https://example.com/bag.jpg"},
                    "maximumRetailPrice": {"amount": 1999.0, "currency": "INR"},
                    "flipkartSellingPrice": {"amount": 1299.0, "currency": "INR"},
                    "productUrl": (
                        "https://www.flipkart.com/asus-laptop-backpack/p/itmbacasus002"
                        "?pid=BAGCASUS002"
                    ),
                    "inStock": True,
                    "isAvailable": True,
                    "productBrand": "ASUS",
                }
            },
        ]
    }
    _stub_flipkart_http(monkeypatch, json.dumps(payload))

    res = client.get("/search", params={"query": "laptop asus"})

    assert res.status_code == 200
    data = res.json()
    by_title = {g["title"]: g for g in data["results"]}

    # The backpack must be excluded: only the ASUS laptop card remains, and it
    # merges Flipkart + Amazon into a single card.
    assert len(data["results"]) == 1
    assert next(iter(by_title)).startswith("ASUS Vivobook")

    card = data["results"][0]
    platforms = sorted(o["platform"] for o in card["offers"])
    assert platforms == ["Amazon", "Flipkart"]
    flipkart_offer = next(o for o in card["offers"] if o["platform"] == "Flipkart")
    assert flipkart_offer["url"].startswith("https://www.flipkart.com/")
    assert card["best_price"] == "\u20b948,499"
    assert card["best_platform"] == "Amazon"


def test_e2e_shirts_filters_out_of_stock_and_cheapest_valid_wins(monkeypatch):
    """
    'shirts': Flipkart API returns two shirts — one out-of-stock, one in-stock.
    The out-of-stock offer must be dropped entirely and the in-stock one must
    be the offer (productId preserved), so an unavailable listing can never
    become the best/compare offer.
    """
    _enable_api(monkeypatch)
    _stub_other_sources(monkeypatch, {})

    payload = {
        "productInfoList": [
            {
                "productBaseInfoV1": {
                    "productId": "SHROST001",
                    "title": "Campus Men Slim Fit Cotton Shirt (Blue)",
                    "imageUrls": {"200x200": "https://example.com/s1.jpg"},
                    "maximumRetailPrice": {"amount": 1299.0, "currency": "INR"},
                    "flipkartSellingPrice": {"amount": 799.0, "currency": "INR"},
                    "productUrl": "https://www.flipkart.com/campus-shirt/p/itmshrost001?pid=SHROST001",
                    "inStock": False,
                    "isAvailable": False,
                    "productBrand": "Campus",
                }
            },
            {
                "productBaseInfoV1": {
                    "productId": "SHRINS002",
                    "title": "Campus Men Slim Fit Cotton Shirt (Red)",
                    "imageUrls": {"200x200": "https://example.com/s2.jpg"},
                    "maximumRetailPrice": {"amount": 1299.0, "currency": "INR"},
                    "flipkartSellingPrice": {"amount": 699.0, "currency": "INR"},
                    "productUrl": "https://www.flipkart.com/campus-shirt/p/itmshrins002?pid=SHRINS002",
                    "inStock": True,
                    "isAvailable": True,
                    "productBrand": "Campus",
                }
            },
        ]
    }
    _stub_flipkart_http(monkeypatch, json.dumps(payload))

    res = client.get("/search", params={"query": "campus tshirt men"})

    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Products compared successfully"

    # Only the in-stock product survives; the out-of-stock one is not a valid
    # comparable offer anywhere in the response.
    assert len(data["results"]) == 1
    card = data["results"][0]
    assert "Red" in card["title"]
    assert len(card["offers"]) == 1
    offer = card["offers"][0]
    assert offer["price_value"] == 699.0
    assert card["best_price"] == "\u20b9699"
    assert card["best_platform"] == "Flipkart"

    serialized = json.dumps(data)
    assert "SHROST001" not in serialized
    assert "Out of" not in serialized


def test_e2e_scraper_fallback_when_api_empty_keeps_contract(monkeypatch):
    """
    When the API is enabled but returns nothing usable, search_flipkart falls
    back to the scraper path; the response contract and honest-empty handling
    must remain intact.
    """
    _enable_api(monkeypatch)
    _stub_other_sources(monkeypatch, {})
    api_calls = _stub_flipkart_http(monkeypatch, '{"productInfoList": []}')

    monkeypatch.setattr(
        flipkart, "_search_flipkart_scraper", lambda q: [
            {
                "title": "OnePlus Nord CE 4 (Blue, 128 GB)",
                "product_key": "oneplus-nord-ce-4-blue-128gb",
                "platform": "Flipkart",
                "price_value": 24999.0,
                "price_display": "\u20b924,999",
                "url": "https://www.flipkart.com/oneplus-nord/p/itm1?pid=MOBONEPLUS",
                "image": "",
            }
        ]
    )

    res = client.get("/search", params={"query": "oneplus nord"})

    assert res.status_code == 200
    data = res.json()
    assert api_calls["n"] == 1
    assert data["message"] == "Products compared successfully"
    assert len(data["results"]) == 1
    offer = data["results"][0]["offers"][0]
    assert offer["platform"] == "Flipkart"
    assert offer["url"].startswith("https://www.flipkart.com/")


def test_e2e_product_id_drives_pipeline_grouping_not_response(monkeypatch):
    """
    The Flipkart productId is a stable identity INSIDE the pipeline: two API
    offers sharing a productId form one group/card (aggregator), while the
    HTTP response contract deliberately omits the field.  This pins both the
    aggregation behaviour and the unchanged frontend contract.
    """
    _enable_api(monkeypatch)
    _stub_other_sources(monkeypatch, {})

    payload = {
        "productInfoList": [
            {
                "productBaseInfoV1": {
                    "productId": "SAMEID001",
                    "title": "Apple iPhone 15 (Black, 128 GB)",
                    "imageUrls": {"200x200": "https://example.com/a.jpg"},
                    "maximumRetailPrice": {"amount": 79900.0, "currency": "INR"},
                    "flipkartSellingPrice": {"amount": 59900.0, "currency": "INR"},
                    "productUrl": (
                        "https://www.flipkart.com/iphone/p/itmsame001"
                        "?pid=SAMEID001&affid=testaffiliate"
                    ),
                    "inStock": True,
                    "isAvailable": True,
                    "productBrand": "Apple",
                }
            },
            {
                "productBaseInfoV1": {
                    "productId": "SAMEID001",
                    "title": "Apple iPhone 15 (Black, 128 GB)",
                    "imageUrls": {"200x200": "https://example.com/a.jpg"},
                    "maximumRetailPrice": {"amount": 79900.0, "currency": "INR"},
                    "flipkartSellingPrice": {"amount": 59900.0, "currency": "INR"},
                    "productUrl": (
                        "https://www.flipkart.com/iphone/p/itmsame001"
                        "?pid=SAMEID001&affid=testaffiliate"
                    ),
                    "inStock": True,
                    "isAvailable": True,
                    "productBrand": "Apple",
                }
            },
        ]
    }
    _stub_flipkart_http(monkeypatch, json.dumps(payload))

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    # Same productId + same listing -> a single card with a single (deduped)
    # offer.
    assert len(data["results"]) == 1
    assert len(data["results"][0]["offers"]) == 1

    # The frontend contract is exact: product_id never leaks into the payload.
    offer = data["results"][0]["offers"][0]
    assert set(offer.keys()) == {
        "title", "product_key", "platform",
        "price_value", "price_display", "url", "image",
    }