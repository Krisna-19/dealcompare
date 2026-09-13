"""
Deterministic Myntra HTTP retrieval tests.

Cover: embedded `window.__myx` JSON extraction, product normalization, price
handling, empty/invalid responses, and the MYNTRA_DATA_SOURCE routing.

Default "http" mode (Phase C) is browser-free: HTTP failure returns honest
empty [] and Playwright is NEVER invoked.  The legacy "scraper" mode (HTTP
primary + Playwright fallback) is tested separately under
MYNTRA_DATA_SOURCE=scraper.

No live network calls.  The HTTP layer is stubbed (monkeypatch on
app.scrapers.myntra.requests.get) and the Playwright scraper is replaced with
a fake so the legacy fallback path is exercised without a browser.
"""

import json
import pathlib

import requests
import pytest

import app.scrapers.myntra as myntra
from app.core.config import get_settings


FIXTURES = pathlib.Path(__file__).parent / "fixtures"
HTML_FIXTURE = FIXTURES / "myntra_search_products.html"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Env-var tests mutate settings; never leak the cache across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _load_html_fixture() -> str:
    return HTML_FIXTURE.read_text(encoding="utf-8")


def _wrap_html(products_json) -> str:
    """Build a minimal Myntra HTML page embedding a window.__myx blob."""
    body = json.dumps({"searchData": {"results": {"products": products_json}}})
    return (
        "<html><body><script type=\"text/javascript\">"
        "window.__myx = " + body + ";</script></body></html>"
    )


# --- Embedded JSON extraction -------------------------------------------------

def test_extract_html_products_from_fixture():
    raw = myntra._extract_html_products(_load_html_fixture(), "shirt")
    assert len(raw) == 4


def test_extract_maps_fields_correctly():
    raw = myntra._extract_html_products(_load_html_fixture(), "shirt")
    first = next(r for r in raw if r["brand"] == "Marks & Spencer")
    assert first["name"].startswith("Marks & Spencer")
    assert first["price_text"] == "₹899"
    assert first["url"].startswith("shirts/marks+%26+spencer")
    assert first["image"].startswith("https://")


def test_extract_upgrades_http_image_to_https():
    raw = myntra._extract_html_products(_load_html_fixture(), "shirt")
    for r in raw:
        assert not r["image"].startswith("http://"), r["image"]


def test_extract_empty_html_returns_empty():
    assert myntra._extract_html_products("", "shirt") == []
    assert myntra._extract_html_products(None, "shirt") == []


def test_extract_html_without_myx_returns_empty():
    assert myntra._extract_html_products("<html>no data</html>", "shirt") == []


def test_extract_corrupt_json_returns_empty():
    bad = "<script>window.__myx = {not valid json;</script>"
    assert myntra._extract_html_products(bad, "shirt") == []


def test_extract_no_products_key_returns_empty():
    html = _wrap_html({})  # products not a list
    assert myntra._extract_html_products(html, "shirt") == []


# --- Product normalization (reuses existing normaliser) -----------------------

def test_normalise_produces_real_offers():
    raw = myntra._extract_html_products(_load_html_fixture(), "shirt")
    offers = myntra._normalise_html_products(raw, "shirt")

    assert len(offers) == 2
    assert all(o["platform"] == "Myntra" for o in offers)
    assert all(o["price_value"] > 0 for o in offers)
    assert all(o["url"].startswith("https://www.myntra.com/") for o in offers)


def test_normalise_uses_configured_base_url(monkeypatch):
    monkeypatch.setenv("MYNTRA_BASE_URL", "https://myntra.example.test")
    raw = myntra._extract_html_products(_load_html_fixture(), "shirt")
    offers = myntra._normalise_html_products(raw, "shirt")
    assert offers
    assert offers[0]["url"].startswith("https://myntra.example.test/")


def test_normalise_drops_zeroprice_product():
    raw = myntra._extract_html_products(_load_html_fixture(), "shirt")
    offers = myntra._normalise_html_products(raw, "shirt")
    titles = [o["title"] for o in offers]
    assert not any("No Price Shirt" in t for t in titles)


def test_normalise_drops_missing_url_product():
    raw = myntra._extract_html_products(_load_html_fixture(), "shirt")
    offers = myntra._normalise_html_products(raw, "shirt")
    titles = [o["title"] for o in offers]
    assert not any("Missing URL" in t for t in titles)


def test_extract_falls_back_to_mrp_when_price_zero():
    product = {
        "productName": "Some Free-ish Item",
        "brand": "Acme",
        "landingPageUrl": "shirts/acme/some-item/111/buy",
        "searchImage": "http://assets.myntassets.com/x.jpg",
        "price": 0,
        "mrp": 999,
    }
    raw = myntra._extract_html_products(_wrap_html([product]), "shirt")
    assert raw[0]["price_text"] == "₹999"


# --- Price handling via normaliser --------------------------------------------

def test_price_parses_rupee_amount():
    value, display = myntra._parse_price("₹899")
    assert value == 899
    assert display == "₹899"


def test_price_missing_yields_check_price():
    value, display = myntra._parse_price("")
    assert value == 0
    assert display == "Check price"


# --- search_myntra dispatch: default http mode (Phase C) --------------------

class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"


def _stub_scraper(monkeypatch, result):
    monkeypatch.setattr(myntra, "_search_myntra_scraper", lambda query: result)


def test_search_uses_http_when_data_present(monkeypatch):
    http_calls = {"n": 0}
    scraper_calls = {"n": 0}

    def fake_get(url, **kwargs):
        http_calls["n"] += 1
        return FakeResponse(200, _load_html_fixture())

    monkeypatch.setattr(myntra.requests, "get", fake_get)

    def fake_scraper(query):
        scraper_calls["n"] += 1
        return []

    monkeypatch.setattr(myntra, "_search_myntra_scraper", fake_scraper)

    results = myntra.search_myntra("shirt")

    assert http_calls["n"] == 1
    assert scraper_calls["n"] == 0
    assert len(results) == 2
    assert results[0]["platform"] == "Myntra"


def test_search_http_mode_honest_empty_on_non_200(monkeypatch):
    """Phase C default: no Playwright fallback; a failed HTTP path is [].

    The scraper being stubbed to return data proves it is never reached.
    """
    scraper_calls = {"n": 0}

    def fake_get(url, **kwargs):
        return FakeResponse(403, "denied")

    monkeypatch.setattr(myntra.requests, "get", fake_get)

    def fake_scraper(query):
        scraper_calls["n"] += 1
        return [{"title": "scraper-fallback"}]

    monkeypatch.setattr(myntra, "_search_myntra_scraper", fake_scraper)

    results = myntra.search_myntra("shirt")
    assert results == []  # honest empty, never fabricated, never browser-backed
    assert scraper_calls["n"] == 0


def test_search_http_mode_honest_empty_when_http_raises(monkeypatch):
    scraper_calls = {"n": 0}

    def boom(url, **kwargs):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(myntra.requests, "get", boom)

    def fake_scraper(query):
        scraper_calls["n"] += 1
        return [{"title": "scraper-fallback"}]

    monkeypatch.setattr(myntra, "_search_myntra_scraper", fake_scraper)

    results = myntra.search_myntra("shirt")
    assert results == []
    assert scraper_calls["n"] == 0


def test_search_http_mode_honest_empty_when_http_empty_results(monkeypatch):
    # 200 but the HTML contains no products -> invalid/empty -> [].
    def fake_get(url, **kwargs):
        return FakeResponse(200, "<html>no products here</html>")

    monkeypatch.setattr(myntra.requests, "get", fake_get)
    _stub_scraper(monkeypatch, [{"title": "scraper-fallback"}])

    assert myntra.search_myntra("shirt") == []


def test_search_http_mode_honest_empty_when_http_products_unusable(monkeypatch):
    # 200 with a products list that normalises to nothing -> [].
    empty_products = _wrap_html([
        {"productName": "No Price", "brand": "B", "price": 0, "mrp": 0}
    ])

    def fake_get(url, **kwargs):
        return FakeResponse(200, empty_products)

    monkeypatch.setattr(myntra.requests, "get", fake_get)
    _stub_scraper(monkeypatch, [{"title": "scraper-fallback"}])

    assert myntra.search_myntra("shirt") == []


def test_search_http_mode_returns_a_list_without_credentials(monkeypatch):
    # search_myntra does not depend on credentials; ensure it returns a list
    # (here empty) and never raises.
    monkeypatch.setattr(
        myntra.requests, "get", lambda url, **kw: FakeResponse(200, "no data")
    )
    _stub_scraper(monkeypatch, [])
    assert isinstance(myntra.search_myntra("anything"), list)


# --- search_myntra dispatch: legacy scramper mode ---------------------------

def test_search_scraper_mode_falls_back_when_http_fails(monkeypatch):
    """MYNTRA_DATA_SOURCE=scraper preserves the HTTP-primary + Playwright
    fallback behaviour the connector used to have by default."""
    monkeypatch.setenv("MYNTRA_DATA_SOURCE", "scraper")

    def fake_get(url, **kwargs):
        return FakeResponse(403, "denied")

    monkeypatch.setattr(myntra.requests, "get", fake_get)
    _stub_scraper(monkeypatch, [{"title": "scraper-fallback"}])

    results = myntra.search_myntra("shirt")
    assert results == [{"title": "scraper-fallback"}]


def test_search_scraper_mode_uses_http_first_when_available(monkeypatch):
    monkeypatch.setenv("MYNTRA_DATA_SOURCE", "scraper")
    http_calls = {"n": 0}
    scraper_calls = {"n": 0}

    def fake_get(url, **kwargs):
        http_calls["n"] += 1
        return FakeResponse(200, _load_html_fixture())

    monkeypatch.setattr(myntra.requests, "get", fake_get)
    _stub_scraper(monkeypatch, [])

    results = myntra.search_myntra("shirt")

    assert http_calls["n"] == 1
    assert len(results) == 2


# --- product_id + original_price (Phase C / Phase G contract) ---------------

def test_normalise_exposes_source_product_id_from_url():
    raw = {
        "brand": "Farah",
        "name": "Slim Fit Chinos",
        "price_text": "\u20b91,299",
        "url": "/mens-chinos/farah/49429950/buy",
        "image": "",
    }
    offer = myntra.normalise_myntra_product(raw, "chinos")
    assert offer is not None
    assert offer["product_id"] == "49429950"
    assert offer["marketplace_product_id"] == "49429950"


@pytest.mark.parametrize("url,expected", [
    ("/mens-chinos/farah/49429950/buy", "49429950"),
    ("/mens-chinos/farah/49429950", "49429950"),
    ("/p/123/buy?color=1", "123"),
    ("https://www.myntra.com/mens-chinos/farah/49429950/buy", "49429950"),
    ("/no-id-in-path/", ""),
    ("", ""),
])
def test_product_id_from_url(url, expected):
    assert myntra._product_id_from_url(url) == expected


def test_normalise_sets_original_price_from_mrp():
    raw = {
        "brand": "Farah",
        "name": "Slim Fit Chinos",
        "price_text": "\u20b91,299",
        "url": "/mens-chinos/farah/49429950/buy",
        "mrp": 2999.0,
    }
    offer = myntra.normalise_myntra_product(raw, "chinos", source_kind="http")
    assert offer["original_price"] == 2999.0
    assert offer["currency"] == "INR"
    assert offer["source_kind"] == "http"


def test_normalise_omits_original_price_when_mrp_below_price():
    raw = {
        "brand": "Farah",
        "name": "Slim Fit Chinos",
        "price_text": "\u20b91,299",
        "url": "/mens-chinos/farah/49429950/buy",
        "mrp": 900.0,  # below selling price -> not a real list price
    }
    offer = myntra.normalise_myntra_product(raw, "chinos")
    assert offer["original_price"] is None
