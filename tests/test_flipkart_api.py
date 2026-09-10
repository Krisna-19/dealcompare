"""
Deterministic Flipkart Affiliate API tests.

Cover: URL building, credential/data-source gating, response parsing,
normalisation, dispatcher (API-first) selection, and API -> scraper fallback.

No live network calls.  The HTTP layer is stubbed (monkeypatch on
requests.get) and the Playwright scraper is replaced with a fake so the
dispatcher fallback path is exercised without launching a browser.
"""

import json
import pathlib

import pytest

import app.scrapers.flipkart as flipkart
from app.scrapers import flipkart_api
from app.core.config import get_settings


FIXTURES = pathlib.Path(__file__).parent / "fixtures"
API_FIXTURE = FIXTURES / "flipkart_api_response.json"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Env-var tests mutate settings; never leak the cache across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _load_api_fixture():
    with open(API_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def _enable_api(monkeypatch):
    """Turn on the API data source with dummy (non-empty) credentials."""
    monkeypatch.setenv("FLIPKART_DATA_SOURCE", "api")
    monkeypatch.setenv("FLIPKART_AFFILIATE_ID", "testaffiliate")
    monkeypatch.setenv("FLIPKART_AFFILIATE_TOKEN", "testtoken")


# --- URL building ----------------------------------------------------------

def test_build_api_search_url():
    url = flipkart_api.build_api_search_url("iphone 15")
    assert url == (
        "https://affiliate-api.flipkart.net/affiliate/1.0/search.json"
        "?query=iphone%2015&resultCount=10"
    )


def test_build_api_search_url_respects_configured_base(monkeypatch):
    monkeypatch.setenv(
        "FLIPKART_API_BASE_URL", "https://affiliate.example.test/affiliate/1.0"
    )
    url = flipkart_api.build_api_search_url("samsung", result_count=5)
    assert url.startswith("https://affiliate.example.test/affiliate/1.0")
    assert "resultCount=5" in url


def test_build_api_search_url_custom_result_count():
    url = flipkart_api.build_api_search_url("shirt", result_count=3)
    assert "resultCount=3" in url


# --- Credential / data-source gating ---------------------------------------

def test_api_disabled_without_data_source(monkeypatch):
    monkeypatch.setenv("FLIPKART_AFFILIATE_ID", "testaffiliate")
    monkeypatch.setenv("FLIPKART_AFFILIATE_TOKEN", "testtoken")
    # FLIPKART_DATA_SOURCE unset -> default scraper -> API disabled.
    assert flipkart_api.api_enabled() is False


def test_api_disabled_with_missing_id(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setenv("FLIPKART_AFFILIATE_ID", "")
    assert flipkart_api.api_enabled() is False


def test_api_disabled_with_missing_token(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setenv("FLIPKART_AFFILIATE_TOKEN", "   ")
    assert flipkart_api.api_enabled() is False


def test_api_enabled_only_when_source_and_credentials(monkeypatch):
    _enable_api(monkeypatch)
    assert flipkart_api.api_enabled() is True


# --- Response parsing -------------------------------------------------------

def test_parse_missing_text_returns_empty():
    assert flipkart_api._parse_search_response(None) == []
    assert flipkart_api._parse_search_response("") == []


def test_parse_invalid_json_returns_empty():
    assert flipkart_api._parse_search_response("not json") == []


def test_parse_non_object_returns_empty():
    assert flipkart_api._parse_search_response("[1,2,3]") == []


def test_parse_valid_fixture_returns_entries():
    raw = _load_api_fixture()
    entries = flipkart_api._parse_search_response(json.dumps(raw))
    assert len(entries) == 3
    assert all(isinstance(e, dict) for e in entries)


def test_parse_missing_product_info_list_returns_empty():
    assert flipkart_api._parse_search_response('{"other": 1}') == []


# --- Normalisation ----------------------------------------------------------

def test_normalise_first_product():
    raw = _load_api_fixture()["productInfoList"][0]
    result = flipkart_api._normalise_api_product(raw)

    assert result is not None
    assert result["platform"] == "Flipkart"
    assert result["title"] == "Apple iPhone 15 (Black, 128 GB)"
    assert result["price_value"] == 59900
    assert result["price_display"] == "₹59,900"
    assert result["url"].startswith("https://www.flipkart.com/")
    assert result["image"].startswith("https://")
    assert result["product_key"] == "apple-15-128gb"
    assert result["product_id"] == "MOBFHG3DGYYFNVQQ"


def test_normalise_prefers_selling_price_over_mrp():
    raw = _load_api_fixture()["productInfoList"][1]
    result = flipkart_api._normalise_api_product(raw)
    # MRP is 79900; selling price 59900 must win.
    assert result["price_value"] == 59900


def test_normalise_empty_dict_returns_none():
    assert flipkart_api._normalise_api_product({}) is None


def test_normalise_missing_title_returns_none():
    raw = {"productBaseInfoV1": {"flipkartSellingPrice": {"amount": 100}}}
    assert flipkart_api._normalise_api_product(raw) is None


def test_normalise_missing_url_returns_none():
    raw = {
        "productBaseInfoV1": {
            "title": "Some Product",
            "flipkartSellingPrice": {"amount": 100},
        }
    }
    assert flipkart_api._normalise_api_product(raw) is None


def test_normalise_zero_price_uses_mrp(monkeypatch):
    _enable_api(monkeypatch)
    raw = {
        "productBaseInfoV1": {
            "title": "Discounted Item",
            "flipkartSellingPrice": {"amount": 0},
            "maximumRetailPrice": {"amount": 5000},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
        }
    }
    result = flipkart_api._normalise_api_product(raw)
    assert result is not None
    assert result["price_value"] == 5000


# --- productId extraction ---------------------------------------------------

def test_normalise_extracts_product_id():
    raw = _load_api_fixture()["productInfoList"][0]
    result = flipkart_api._normalise_api_product(raw)
    assert result["product_id"] == "MOBFHG3DGYYFNVQQ"


def test_normalise_product_id_none_when_missing():
    raw = {
        "productBaseInfoV1": {
            "title": "No ID Product",
            "flipkartSellingPrice": {"amount": 100},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
        }
    }
    result = flipkart_api._normalise_api_product(raw)
    assert result is not None
    assert result["product_id"] is None


def test_normalise_product_id_none_when_empty_string():
    raw = {
        "productBaseInfoV1": {
            "title": "Empty ID Product",
            "flipkartSellingPrice": {"amount": 100},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
            "productId": "",
        }
    }
    result = flipkart_api._normalise_api_product(raw)
    assert result is not None
    assert result["product_id"] is None


def test_normalise_product_id_none_when_whitespace():
    raw = {
        "productBaseInfoV1": {
            "title": "Whitespace ID Product",
            "flipkartSellingPrice": {"amount": 100},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
            "productId": "   ",
        }
    }
    result = flipkart_api._normalise_api_product(raw)
    assert result is not None
    assert result["product_id"] is None


def test_all_fixture_products_have_product_id():
    for entry in _load_api_fixture()["productInfoList"]:
        result = flipkart_api._normalise_api_product(entry)
        assert result is not None
        assert result["product_id"] is not None
        assert len(result["product_id"]) > 0


# --- inStock / isAvailable filtering ----------------------------------------

def test_normalise_filters_out_of_stock():
    raw = {
        "productBaseInfoV1": {
            "title": "Out of Stock Widget",
            "flipkartSellingPrice": {"amount": 999},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
            "inStock": False,
        }
    }
    assert flipkart_api._normalise_api_product(raw) is None


def test_normalise_filters_unavailable_product():
    raw = {
        "productBaseInfoV1": {
            "title": "Unavailable Widget",
            "flipkartSellingPrice": {"amount": 999},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
            "isAvailable": False,
        }
    }
    assert flipkart_api._normalise_api_product(raw) is None


def test_normalise_filters_both_false():
    raw = {
        "productBaseInfoV1": {
            "title": "Dead Product",
            "flipkartSellingPrice": {"amount": 999},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
            "inStock": False,
            "isAvailable": False,
        }
    }
    assert flipkart_api._normalise_api_product(raw) is None


def test_normalise_keeps_in_stock_true():
    raw = {
        "productBaseInfoV1": {
            "title": "In Stock Product",
            "flipkartSellingPrice": {"amount": 999},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
            "inStock": True,
            "isAvailable": True,
        }
    }
    assert flipkart_api._normalise_api_product(raw) is not None


def test_normalise_keeps_missing_stock_fields():
    """Products with no inStock/isAvailable field are kept (assume in-stock)."""
    raw = {
        "productBaseInfoV1": {
            "title": "Unknown Stock Product",
            "flipkartSellingPrice": {"amount": 999},
            "productUrl": "https://www.flipkart.com/x/p/itm1",
        }
    }
    assert flipkart_api._normalise_api_product(raw) is not None


def test_search_filters_out_of_stock_from_results(monkeypatch):
    """Out-of-stock products must not appear in search results."""
    _enable_api(monkeypatch)
    mixed_response = {
        "productInfoList": [
            {
                "productBaseInfoV1": {
                    "productId": "INSTOCK001",
                    "title": "In Stock Phone",
                    "flipkartSellingPrice": {"amount": 15000},
                    "productUrl": "https://www.flipkart.com/phone/p/itm1",
                    "inStock": True,
                }
            },
            {
                "productBaseInfoV1": {
                    "productId": "OOSTOCK002",
                    "title": "Out of Stock Phone",
                    "flipkartSellingPrice": {"amount": 12000},
                    "productUrl": "https://www.flipkart.com/phone/p/itm2",
                    "inStock": False,
                }
            },
        ]
    }
    monkeypatch.setattr(
        flipkart_api.requests,
        "get",
        lambda url, **kwargs: FakeResponse(200, json.dumps(mixed_response)),
    )
    results = flipkart_api.search_flipkart_api("phone")
    assert len(results) == 1
    assert results[0]["product_id"] == "INSTOCK001"
    assert results[0]["title"] == "In Stock Phone"


# --- Request handling (stubbed HTTP) ---------------------------------------

class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_search_returns_results_on_success(monkeypatch):
    _enable_api(monkeypatch)
    fixture = json.dumps(_load_api_fixture())

    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        assert kwargs["headers"]["Fk-Affiliate-Id"] == "testaffiliate"
        assert kwargs["headers"]["Fk-Affiliate-Token"] == "testtoken"
        return FakeResponse(200, fixture)

    monkeypatch.setattr(flipkart_api.requests, "get", fake_get)

    results = flipkart_api.search_flipkart_api("iphone")
    assert isinstance(results, list)
    assert len(results) >= 1
    assert results[0]["title"] == "Apple iPhone 15 (Black, 128 GB)"


def test_search_returns_empty_on_http_error(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        flipkart_api.requests, "get", lambda url, **kwargs: FakeResponse(401, "")
    )
    assert flipkart_api.search_flipkart_api("iphone") == []


def test_search_returns_empty_on_request_exception(monkeypatch):
    _enable_api(monkeypatch)

    import requests

    def boom(url, **kwargs):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(flipkart_api.requests, "get", boom)
    assert flipkart_api.search_flipkart_api("iphone") == []


def test_search_returns_empty_on_invalid_body(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        flipkart_api.requests, "get", lambda url, **kwargs: FakeResponse(200, "junk")
    )
    assert flipkart_api.search_flipkart_api("iphone") == []


# --- Dispatcher: API-first + scraper fallback ------------------------------

def _stub_scraper(monkeypatch, result):
    """Replace the real Playwright scraper with a deterministic fake."""
    monkeypatch.setattr(
        flipkart, "_search_flipkart_scraper", lambda query: result
    )


def test_search_flipkart_uses_api_when_enabled(monkeypatch):
    _enable_api(monkeypatch)
    fixture = json.dumps(_load_api_fixture())
    api_calls = {"n": 0}
    scraper_calls = {"n": 0}

    def fake_get(url, **kwargs):
        api_calls["n"] += 1
        return FakeResponse(200, fixture)

    monkeypatch.setattr(flipkart_api.requests, "get", fake_get)

    def fake_scraper(query):
        scraper_calls["n"] += 1
        return [{"title": "scraper-only"}]

    monkeypatch.setattr(flipkart, "_search_flipkart_scraper", fake_scraper)

    results = flipkart.search_flipkart("iphone")

    assert api_calls["n"] == 1
    assert scraper_calls["n"] == 0
    assert results and results[0]["title"] == "Apple iPhone 15 (Black, 128 GB)"


def test_search_flipkart_falls_back_when_api_empty(monkeypatch):
    _enable_api(monkeypatch)
    api_calls = {"n": 0}

    def fake_get(url, **kwargs):
        api_calls["n"] += 1
        return FakeResponse(200, '{"productInfoList": []}')

    monkeypatch.setattr(flipkart_api.requests, "get", fake_get)
    _stub_scraper(monkeypatch, [{"title": "from-scraper"}])

    results = flipkart.search_flipkart("iphone")

    assert api_calls["n"] == 1
    assert results == [{"title": "from-scraper"}]


def test_search_flipkart_falls_back_when_api_http_error(monkeypatch):
    _enable_api(monkeypatch)

    import requests

    def fake_get(url, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(flipkart_api.requests, "get", fake_get)
    _stub_scraper(monkeypatch, [{"title": "from-scraper"}])

    results = flipkart.search_flipkart("iphone")
    assert results == [{"title": "from-scraper"}]


def test_search_flipkart_falls_back_when_api_returns_nothing(monkeypatch):
    _enable_api(monkeypatch)

    def fake_get(url, **kwargs):
        return FakeResponse(200, "")

    monkeypatch.setattr(flipkart_api.requests, "get", fake_get)
    _stub_scraper(monkeypatch, [])

    assert flipkart.search_flipkart("iphone") == []


def test_search_flipkart_uses_scraper_when_credentials_missing(monkeypatch):
    monkeypatch.setenv("FLIPKART_DATA_SOURCE", "api")
    # No credentials set -> API disabled.
    _stub_scraper(monkeypatch, [{"title": "scraper-result"}])
    assert flipkart.search_flipkart("iphone") == [{"title": "scraper-result"}]


def test_search_flipkart_uses_scraper_by_default(monkeypatch):
    # FLIPKART_DATA_SOURCE unset -> default scraper.
    _stub_scraper(monkeypatch, [{"title": "scraper-result"}])
    assert flipkart.search_flipkart("iphone") == [{"title": "scraper-result"}]


def test_search_flipkart_returns_empty_when_scraper_empty(monkeypatch):
    _stub_scraper(monkeypatch, [])
    assert flipkart.search_flipkart("iphone") == []


# --- Product URL / tracking handling ----------------------------------------

def test_normalise_preserves_full_product_url():
    raw = _load_api_fixture()["productInfoList"][0]
    result = flipkart_api._normalise_api_product(raw)
    url = result["url"]
    assert url.startswith("https://www.flipkart.com/")
    assert "pid=" in url
    assert "MOBFHG3DGYYFNVQQ" in url


def test_search_api_url_includes_encoded_query(monkeypatch):
    """The built URL must percent-encode the query string."""
    url = flipkart_api.build_api_search_url("samsung galaxy s24")
    assert "samsung%20galaxy%20s24" in url


def test_search_returns_results_from_fixture(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        flipkart_api.requests,
        "get",
        lambda url, **kwargs: FakeResponse(200, json.dumps(_load_api_fixture())),
    )
    results = flipkart_api.search_flipkart_api("iphone")
    assert len(results) >= 2
    titles = [r["title"] for r in results]
    assert "Apple iPhone 15 (Black, 128 GB)" in titles
    assert "Apple iPhone 15 (Blue, 128 GB)" in titles


def test_search_api_returns_empty_list(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        flipkart_api.requests,
        "get",
        lambda url, **kwargs: FakeResponse(200, '{"productInfoList": []}'),
    )
    assert flipkart_api.search_flipkart_api("obscure-query-xyz") == []


def test_search_api_returns_empty_on_none_body(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        flipkart_api.requests,
        "get",
        lambda url, **kwargs: FakeResponse(200, ""),
    )
    assert flipkart_api.search_flipkart_api("test") == []


# --- Error / edge-case responses -------------------------------------------

def test_search_returns_empty_on_500(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        flipkart_api.requests,
        "get",
        lambda url, **kwargs: FakeResponse(500, '{"error": "Internal Server Error"}'),
    )
    assert flipkart_api.search_flipkart_api("phone") == []


def test_search_returns_empty_on_429(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        flipkart_api.requests,
        "get",
        lambda url, **kwargs: FakeResponse(429, ""),
    )
    assert flipkart_api.search_flipkart_api("phone") == []


def test_search_returns_empty_on_empty_product_list(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        flipkart_api.requests,
        "get",
        lambda url, **kwargs: FakeResponse(200, '{"productInfoList": []}'),
    )
    assert flipkart_api.search_flipkart_api("phone") == []


def test_parse_non_list_product_info_returns_empty():
    assert flipkart_api._parse_search_response('{"productInfoList": "bad"}') == []


def test_parse_none_product_info_returns_empty():
    assert flipkart_api._parse_search_response('{"productInfoList": null}') == []


# --- Scraper bypass when API enabled -----------------------------------------

def test_playwright_not_imported_when_api_enabled(monkeypatch):
    """When FLIPKART_DATA_SOURCE=api, the Playwright module should not be imported in the API path."""
    _enable_api(monkeypatch)
    fixture = json.dumps(_load_api_fixture())
    monkeypatch.setattr(
        flipkart_api.requests,
        "get",
        lambda url, **kwargs: FakeResponse(200, fixture),
    )
    scraper_imports = {"n": 0}

    def counting_scraper(q):
        scraper_imports["n"] += 1
        return []

    monkeypatch.setattr(flipkart, "_search_flipkart_scraper", counting_scraper)
    flipkart.search_flipkart("iphone")
    assert scraper_imports["n"] == 0


# --- Aggregator: productId-driven grouping -------------------------------------

def _fk_offer(product_id, url, title, price):
    return {
        "title": title,
        "product_key": "apple-iphone-15-128gb",
        "platform": "Flipkart",
        "price_value": price,
        "price_display": f"\u20b9{int(price):,}",
        "url": url,
        "image": "",
        "product_id": product_id,
    }


def test_aggregator_groups_same_product_id_into_one_card():
    """Two Flipkart API offers sharing a productId merge into a single card."""
    from app.aggregator.aggregator import aggregate_products

    a = _fk_offer(
        "MOBPID001",
        "https://www.flipkart.com/iphone/p/itm1?pid=MOBPID001",
        "Apple iPhone 15 (Black, 128 GB)",
        59900,
    )
    b = _fk_offer(
        "MOBPID001",
        "https://www.flipkart.com/iphone/p/itm1?pid=MOBPID001&affid=test",
        "Apple iPhone 15 (Black, 128 GB)",
        59900,
    )

    cards = aggregate_products([a, b])
    assert len(cards) == 1
    assert len(cards[0]["offers"]) == 1


def test_aggregator_keeps_distinct_product_ids_separate():
    """Different productIds (even with the same title) stay as separate cards."""
    from app.aggregator.aggregator import aggregate_products

    black = _fk_offer(
        "MOBPIDBLACK",
        "https://www.flipkart.com/iphone/p/itm1?pid=MOBPIDBLACK",
        "Apple iPhone 15 (Black, 128 GB)",
        59900,
    )
    blue = _fk_offer(
        "MOBPIDBLUE",
        "https://www.flipkart.com/iphone/p/itm2?pid=MOBPIDBLUE",
        "Apple iPhone 15 (Blue, 128 GB)",
        59900,
    )

    cards = aggregate_products([black, blue])
    assert len(cards) == 2


def test_aggregator_merges_product_id_offer_with_cross_store(monkeypatch):
    """
    A Flipkart API offer (with product_id) and an Amazon offer for the same
    SKU still merge into one card — productId must not break cross-marketplace
    grouping.
    """
    from app.aggregator.aggregator import aggregate_products

    fk = _fk_offer(
        "MOBPID001",
        "https://www.flipkart.com/iphone/p/itm1?pid=MOBPID001",
        "Apple iPhone 15 (Black, 128 GB)",
        61999,
    )
    amz = {
        "title": "Apple iPhone 15 (Black, 128 GB)",
        "product_key": "apple-iphone-15-128gb",
        "platform": "Amazon",
        "price_value": 59900.0,
        "price_display": "\u20b959,900",
        "url": "https://www.amazon.in/dp/B0BLACK",
        "image": "https://example.com/a.jpg",
    }

    cards = aggregate_products([fk, amz])
    assert len(cards) == 1
    assert sorted(o["platform"] for o in cards[0]["offers"]) == ["Amazon", "Flipkart"]
    assert cards[0]["best_platform"] == "Amazon"
