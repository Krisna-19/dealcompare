"""
Deterministic Amazon Creators API adapter tests (Phase D).

The Creators API path is exercised with NO live credentials or network: every
HTTP call is stubbed on app.scrapers.amazon_creators.requests.post, keyed off
the request URL (token endpoint vs catalog base).  The adapter must:
  - require AMAZON_DATA_SOURCE=api + all three credentials values,
  - fetch an LwA bearer token once and cache it until near-expiry,
  - normalise offersV2 listings into the shared offer contract,
  - refine price-less search items via GetItems ("when needed"),
  - fail safe (honest empty) on missing creds / bad token / non-200 / junk,
  - never touch the old Playwright scraper while "api" is selected.
"""

import requests
import pytest

from app.core.config import get_settings
from app.scrapers import amazon
import app.scrapers.amazon_creators as creators


class FakeResponse:
    def __init__(self, status_code, json_obj=None, text=""):
        self.status_code = status_code
        self._json = json_obj
        self.text = text
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def json(self):
        if not self._json:
            raise ValueError("no body")
        return self._json


TOKEN_URL = "https://api.amazon.co.uk/auth/o2/token"
CATALOG_URL = "https://creatorsapi.amazon"


@pytest.fixture(autouse=True)
def _clear_state():
    """Fresh settings + token cache per test; never leak env across tests."""
    get_settings.cache_clear()
    creators.clear_token_cache()
    yield
    get_settings.cache_clear()
    creators.clear_token_cache()


def _enable_api(monkeypatch):
    monkeypatch.setenv("AMAZON_DATA_SOURCE", "api")
    monkeypatch.setenv("AMAZON_CREATOR_CLIENT_ID", "test-client")
    monkeypatch.setenv("AMAZON_CREATOR_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AMAZON_PARTNER_TAG", "testtag-21")


def _token_body():
    return {"access_token": "tok_abc123", "expires_in": 3600}


def _item(asin, title, price, available=True, saving=None):
    listings = []
    if price is not None:
        price_obj = {"money": {
            "amount": price,
            "currency": "INR",
            "displayAmount": f"₹{int(price):,.0f}",
        }}
        if saving is not None and saving > price:
            price_obj["savingBasis"] = {"money": {
                "amount": saving,
                "currency": "INR",
                "displayAmount": f"₹{int(saving):,.0f}",
            }}
        listings.append({
            "availability": {
                "type": "IN_STOCK" if available else "OUT_OF_STOCK",
                "message": "In Stock" if available else "Unavailable",
            },
            "price": price_obj,
            "merchantInfo": {"id": "AMZN", "name": "Amazon Retail"},
        })
    return {
        "asin": asin,
        "detailPageURL": f"https://www.amazon.in/dp/{asin}",
        "images": {"primary": {"large": {"url": f"https://media.amazon.in/{asin}.jpg"}}},
        "itemInfo": {"title": {"displayValue": title}},
        **({"offersV2": {"listings": listings}} if listings else {}),
    }


def _search_payload(items):
    return {"searchResult": {"items": items}}


def _post_router(*routes):
    """Build a fake requests.post that routes by URL prefix."""
    token_resp, search_resp, getitems_resp = routes

    def fake_post(url, **kwargs):
        if url == TOKEN_URL:
            return token_resp
        if url.startswith(CATALOG_URL + "/catalog/v1/searchItems"):
            return search_resp
        if url.startswith(CATALOG_URL + "/catalog/v1/getItems"):
            return getitems_resp or FakeResponse(200, {"itemResults": {"items": []}})
        raise AssertionError(f"unexpected POST {url}")

    return fake_post


# --- Enablement -------------------------------------------------------------

def test_api_requires_every_credential(monkeypatch):
    monkeypatch.setenv("AMAZON_DATA_SOURCE", "api")
    monkeypatch.setenv("AMAZON_CREATOR_CLIENT_ID", "x")
    monkeypatch.setenv("AMAZON_CREATOR_CLIENT_SECRET", "")
    monkeypatch.setenv("AMAZON_PARTNER_TAG", "")
    assert not creators.api_credentials_available()
    assert not creators.api_enabled()


def test_api_enabled_with_all_values(monkeypatch):
    _enable_api(monkeypatch)
    assert creators.api_credentials_available()
    assert creators.api_enabled()


def test_search_honest_empty_when_not_enabled(monkeypatch):
    monkeypatch.setenv("AMAZON_DATA_SOURCE", "scraper")
    calls = {"n": 0}
    monkeypatch.setattr(
        creators.requests,
        "post",
        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or FakeResponse(200, {}),
    )
    assert creators.search_amazon_creators("iphone 15") == []
    assert calls["n"] == 0  # no network attempt without enablement


def test_search_honest_empty_when_credentials_missing(monkeypatch):
    monkeypatch.setenv("AMAZON_DATA_SOURCE", "api")  # creds left unset
    calls = {"n": 0}
    monkeypatch.setattr(
        creators.requests,
        "post",
        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or FakeResponse(200, {}),
    )
    assert creators.search_amazon_creators("iphone 15") == []
    assert calls["n"] == 0


# --- Token flow -------------------------------------------------------------

def test_bad_token_response_returns_empty(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        creators.requests,
        "post",
        _post_router(
            FakeResponse(401, {"error": "unauthorized"}),
            FakeResponse(200, _search_payload([_item("B0ABC12345", "iPhone 15 (Black, 128 GB)", 64999)])),
            None,
        ),
    )
    assert creators.search_amazon_creators("iphone 15") == []


def test_token_network_error_returns_empty(monkeypatch):
    _enable_api(monkeypatch)

    def boom(url, **kwargs):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(creators.requests, "post", boom)

    assert creators.search_amazon_creators("iphone 15") == []


def test_token_is_cached_until_expiry(monkeypatch):
    _enable_api(monkeypatch)
    token_calls = {"n": 0}

    def fake_post(url, **kwargs):
        if url == TOKEN_URL:
            token_calls["n"] += 1
            return FakeResponse(200, _token_body())
        if url.startswith(CATALOG_URL + "/catalog/v1/searchItems"):
            return FakeResponse(
                200,
                _search_payload([_item("B0A", "Samsung Galaxy S24 (Onyx Black, 128 GB)", 64999)]),
            )
        return FakeResponse(200, {"itemResults": {"items": []}})

    monkeypatch.setattr(creators.requests, "post", fake_post)

    assert creators.search_amazon_creators("samsung galaxy s24")
    assert creators.search_amazon_creators("samsung galaxy s24")
    token_calls_after = token_calls["n"]
    assert token_calls_after == 1  # second search reused the cached token


# --- SearchItems normalisation ----------------------------------------------

def test_search_normalises_offers(monkeypatch):
    _enable_api(monkeypatch)
    payload = _search_payload([
        _item("B0ABC12345", "Apple iPhone 15 (Black, 128 GB)", 64999, saving=79900),
    ])
    monkeypatch.setattr(
        creators.requests,
        "post",
        _post_router(FakeResponse(200, _token_body()), FakeResponse(200, payload), None),
    )
    results = creators.search_amazon_creators("iphone 15")

    assert len(results) == 1
    offer = results[0]
    assert offer["platform"] == "Amazon"
    assert offer["product_id"] == "B0ABC12345"
    assert offer["marketplace_product_id"] == "B0ABC12345"
    assert offer["price_value"] == 64999.0
    assert offer["original_price"] == 79900.0
    assert offer["availability"] == "in_stock"
    assert offer["currency"] == "INR"
    assert offer["url"] == "https://www.amazon.in/dp/B0ABC12345"
    assert offer["image"].startswith("https://media.amazon.in/")
    assert offer["source_kind"] == "api"


def test_search_skips_out_of_stock_items(monkeypatch):
    _enable_api(monkeypatch)
    payload = _search_payload([
        _item("B0OOS11111", "Apple iPhone 15 (Blue, 128 GB)", 65000, available=False),
        _item("B0IN222222", "Apple iPhone 15 (Black, 128 GB)", 64999),
    ])
    monkeypatch.setattr(
        creators.requests,
        "post",
        _post_router(FakeResponse(200, _token_body()), FakeResponse(200, payload), None),
    )
    results = creators.search_amazon_creators("iphone 15")
    assert [o["product_id"] for o in results] == ["B0IN222222"]


def test_search_empty_items_returns_empty(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        creators.requests,
        "post",
        _post_router(
            FakeResponse(200, _token_body()),
            FakeResponse(200, {"searchResult": {"items": []}}),
            None,
        ),
    )
    assert creators.search_amazon_creators("obscure-xyz") == []


def test_search_junk_catalog_body_returns_empty(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setattr(
        creators.requests,
        "post",
        _post_router(FakeResponse(200, _token_body()), FakeResponse(500, {"error": "x"}), None),
    )
    assert creators.search_amazon_creators("iphone 15") == []


# --- GetItems refinement (when a search item lacks an offer) ----------------

def test_get_items_refines_price_missing_search_item(monkeypatch):
    _enable_api(monkeypatch)
    search_payload = _search_payload([
        _item("B0NOOFF01", "Apple iPhone 15 (White, 128 GB)", price=None),  # no offer
        _item("B0HAVEO01", "Apple iPhone 15 (Black, 128 GB)", 64999),
    ])
    getitems_payload = {"itemResults": {"items": [
        _item("B0NOOFF01", "Apple iPhone 15 (White, 128 GB)", 62000),
    ]}}
    getitems_calls = {"n": 0}

    def fake_post(url, **kwargs):
        if url == TOKEN_URL:
            return FakeResponse(200, _token_body())
        if url.startswith(CATALOG_URL + "/catalog/v1/searchItems"):
            return FakeResponse(200, search_payload)
        if url.startswith(CATALOG_URL + "/catalog/v1/getItems"):
            getitems_calls["n"] += 1
            assert kwargs["json"]["itemIds"] == ["B0NOOFF01"]
            return FakeResponse(200, getitems_payload)
        raise AssertionError(url)

    monkeypatch.setattr(creators.requests, "post", fake_post)

    results = creators.search_amazon_creators("iphone 15")
    assert getitems_calls["n"] == 1
    product_ids = {o["product_id"] for o in results}
    assert "B0NOOFF01" in product_ids
    assert "B0HAVEO01" in product_ids


def test_get_items_lookup_helper(monkeypatch):
    _enable_api(monkeypatch)
    getitems_payload = {"itemResults": {"items": [
        _item("B0LOOK001", "Apple iPhone 15 (Green, 128 GB)", 64000),
    ]}}
    monkeypatch.setattr(
        creators.requests,
        "post",
        _post_router(
            FakeResponse(200, _token_body()),
            FakeResponse(200, {"searchResult": {"items": []}}),
            FakeResponse(200, getitems_payload),
        ),
    )
    offers = creators.get_items("B0LOOK001")
    assert len(offers) == 1
    assert offers[0]["product_id"] == "B0LOOK001"


def test_get_items_matches_asin_field_not_position(monkeypatch):
    """GetItems items are looked up by their `asin` field (documented shape).

    The response order is not guaranteed, so the requested ASIN must be
    matched by the field value — never by array position.
    """
    _enable_api(monkeypatch)
    getitems_payload = {"itemResults": {"items": [
        _item("B0OTHER01", "Apple iPhone 15 (Red, 128 GB)", 61000),
        _item("B0WANT001", "Apple iPhone 15 (Black, 128 GB)", 62000),
    ]}}
    monkeypatch.setattr(
        creators.requests,
        "post",
        _post_router(
            FakeResponse(200, _token_body()),
            FakeResponse(200, {"searchResult": {"items": []}}),
            FakeResponse(200, getitems_payload),
        ),
    )
    offers = creators.get_items("B0WANT001")
    assert len(offers) == 1
    assert offers[0]["product_id"] == "B0WANT001"


def test_get_items_recognises_itemsresult_doc_variant(monkeypatch):
    """Amazon's cURL guide renders the container as `itemsResult`; both parse."""
    _enable_api(monkeypatch)
    getitems_payload = {"itemsResult": {"items": [
        _item("B0CURL001", "Apple iPhone 15 (Purple, 128 GB)", 63000),
    ]}}
    monkeypatch.setattr(
        creators.requests,
        "post",
        _post_router(
            FakeResponse(200, _token_body()),
            FakeResponse(200, {"searchResult": {"items": []}}),
            FakeResponse(200, getitems_payload),
        ),
    )
    offers = creators.get_items("B0CURL001")
    assert len(offers) == 1
    assert offers[0]["product_id"] == "B0CURL001"


def test_get_items_garbage_response_returns_empty(monkeypatch):
    _enable_api(monkeypatch)
    for junk in (None, {"foo": "bar"}, {"itemResults": {"items": "nope"}}):
        monkeypatch.setattr(
            creators.requests,
            "post",
            _post_router(
                FakeResponse(200, _token_body()),
                FakeResponse(200, {"searchResult": {"items": []}}),
                FakeResponse(200, junk) if junk is not None else FakeResponse(200, {}),
            ),
        )
        assert creators.get_items("B0WANT001") == []


def test_search_catalog_429_returns_empty(monkeypatch):
    """Rate-limited/transient catalog failure -> honest empty, no retry loop."""
    _enable_api(monkeypatch)
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        if url == TOKEN_URL:
            return FakeResponse(200, _token_body())
        return FakeResponse(429, {"errors": [{"code": "TooManyRequests"}]})

    monkeypatch.setattr(creators.requests, "post", fake_post)

    assert creators.search_amazon_creators("iphone 15") == []
    assert calls["n"] == 2  # token + exactly ONE catalog call; never a loop


def test_search_get_items_refinement_handles_real_list_shape(monkeypatch):
    """The GetItems refinement parses itemResults.items as a LIST."""
    _enable_api(monkeypatch)
    search_payload = _search_payload([
        _item("B0NOOFF01", "Apple iPhone 15 (White, 128 GB)", price=None),
    ])
    getitems_payload = {"itemResults": {"items": [
        _item("B0NOOFF01", "Apple iPhone 15 (White, 128 GB)", 62000),
    ]}}
    getitems_calls = {"n": 0}

    def fake_post(url, **kwargs):
        if url == TOKEN_URL:
            return FakeResponse(200, _token_body())
        if url.startswith(CATALOG_URL + "/catalog/v1/searchItems"):
            return FakeResponse(200, search_payload)
        if url.startswith(CATALOG_URL + "/catalog/v1/getItems"):
            getitems_calls["n"] += 1
            assert kwargs["json"]["itemIds"] == ["B0NOOFF01"]
            assert kwargs["json"]["marketplace"] == "www.amazon.in"
            return FakeResponse(200, getitems_payload)
        raise AssertionError(url)

    monkeypatch.setattr(creators.requests, "post", fake_post)

    results = creators.search_amazon_creators("iphone 15")
    assert getitems_calls["n"] == 1
    assert {o["product_id"] for o in results} == {"B0NOOFF01"}


# --- Amazon dispatcher (api vs scraper) -------------------------------------

def test_dispatcher_never_uses_scraper_when_api_selected(monkeypatch):
    _enable_api(monkeypatch)
    scraper_calls = {"n": 0}

    def fake_scraper(query):
        scraper_calls["n"] += 1
        return []

    monkeypatch.setattr(amazon, "_search_amazon_scraper", fake_scraper)
    monkeypatch.setattr(
        amazon,
        "_search_amazon_creators",
        lambda query: [{"title": "api-offer"}],
    )

    results = amazon.search_amazon("iphone 15")
    assert results == [{"title": "api-offer"}]
    assert scraper_calls["n"] == 0


def test_dispatcher_uses_api_by_default(monkeypatch):
    # AMAZON_DATA_SOURCE unset -> default "api": the Creators API adapter is
    # selected and the legacy Playwright scraper is never reached.
    scraper_calls = {"n": 0}

    def fake_scraper(query):
        scraper_calls["n"] += 1
        return [{"title": "scraper-offer"}]

    monkeypatch.setattr(amazon, "_search_amazon_scraper", fake_scraper)
    monkeypatch.setattr(amazon, "_search_amazon_creators", lambda q: [{"title": "api"}])

    results = amazon.search_amazon("iphone 15")
    assert results == [{"title": "api"}]
    assert scraper_calls["n"] == 0


# --- Headers / request shape -------------------------------------------------

def test_catalog_request_carries_bearer_and_marketplace_headers(monkeypatch):
    """The bearer token + x-marketplace header must reach the catalog API."""
    _enable_api(monkeypatch)
    seen = {}

    def fake_post(url, **kwargs):
        if url == TOKEN_URL:
            return FakeResponse(200, _token_body())
        seen.update(kwargs.get("headers", {}))
        seen.update({"payload": kwargs.get("json", {})})
        return FakeResponse(200, {"searchResult": {"items": []}})

    monkeypatch.setattr(creators.requests, "post", fake_post)

    creators.search_amazon_creators("samsung")

    assert seen.get("Authorization") == "Bearer tok_abc123"
    assert seen.get("x-marketplace") == "www.amazon.in"
    assert seen["payload"].get("partnerTag") == "testtag-21"
    assert seen["payload"].get("marketplace") == "www.amazon.in"
    assert all(r in seen["payload"]["resources"] for r in (
        "images.primary.large",
        "itemInfo.title",
        "offersV2.listings.availability",
        "offersV2.listings.price",
    ))


def test_catalog_api_base_url_is_configurable(monkeypatch):
    _enable_api(monkeypatch)
    monkeypatch.setenv("AMAZON_CREATORS_API_BASE_URL", "https://creators.example.test")
    seen = {}

    def fake_post(url, **kwargs):
        if "/auth/o2/token" in url:
            return FakeResponse(200, _token_body())
        seen["url"] = url
        return FakeResponse(200, {"searchResult": {"items": []}})

    monkeypatch.setattr(creators.requests, "post", fake_post)

    creators.search_amazon_creators("samsung")

    assert seen["url"].startswith("https://creators.example.test/catalog/v1/searchItems")