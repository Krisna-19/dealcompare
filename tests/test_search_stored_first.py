"""
Stored-offers-first search tests.

The catalog turns /search into a platform that serves historically-observed
real offers without re-scraping while the stored snapshot is fresh.  This suite
pins the exact gating: stored serving honours the search-cache enabled switch,
the freshness window is min(cache TTL, stored freshness), and empty searches
are never persisted.
"""

import asyncio
import time

from app.services import search_service
from app.storage.store import get_store


class _CatalogSettings:
    """Tiny stand-in for app.core.config.Settings covering the catalog path."""

    def __init__(self, cache_enabled=True, ttl_seconds=3600.0,
                 stored_freshness_seconds=86400.0, catalog_enabled=True):
        self.search_cache_enabled = cache_enabled
        self.search_cache_ttl_seconds = ttl_seconds
        self.stored_search_freshness_seconds = stored_freshness_seconds
        self.catalog_enabled = catalog_enabled
        self.scrape_concurrency_limit = 2
        self.source_timeout_seconds = 60.0


def _use_catalog_settings(monkeypatch, **kwargs):
    monkeypatch.setattr(
        search_service, "get_settings", lambda: _CatalogSettings(**kwargs)
    )


def _real(price=79999.0):
    return {
        "title": "Apple iPhone 15 (128 GB) - Black",
        "product_key": "apple-iphone-15-128gb",
        "platform": "Amazon",
        "price_value": price,
        "price_display": "\u20b979,999",
        "url": "https://www.amazon.in/dp/ABC123",
        "image": "https://example.com/a.jpg",
    }


def _stub_others_empty(monkeypatch):
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])


def test_stored_offers_served_without_rescraping(monkeypatch):
    _use_catalog_settings(monkeypatch)
    calls = []

    def amazon(q):
        calls.append(q)
        return [_real()]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    first = asyncio.run(search_service.search_all("iphone 15"))
    search_service.clear_search_cache()  # force the STORED path, not memory cache
    second = asyncio.run(search_service.search_all("iphone 15"))

    assert first == [_real()]
    assert second == [_real()]  # verbatim round-trip of the stored offers
    assert calls == ["iphone 15"]  # served from the catalog: no second scrape

    assert get_store().counts()["offers"] == 1


def test_stored_not_served_when_cache_disabled(monkeypatch):
    _use_catalog_settings(monkeypatch, cache_enabled=False)
    calls = []

    def amazon(q):
        calls.append(q)
        return [_real()]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    asyncio.run(search_service.search_all("iphone 15"))
    search_service.clear_search_cache()
    asyncio.run(search_service.search_all("iphone 15"))

    assert calls == ["iphone 15", "iphone 15"]  # cache-off is stored-off


def test_store_not_enabled_degrades_to_live_only(monkeypatch):
    _use_catalog_settings(monkeypatch, catalog_enabled=False)
    calls = []

    def amazon(q):
        calls.append(q)
        return [_real()]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    asyncio.run(search_service.search_all("iphone 15"))
    search_service.clear_search_cache()
    asyncio.run(search_service.search_all("iphone 15"))

    assert calls == ["iphone 15", "iphone 15"]


def test_stored_entry_expires_after_cache_ttl(monkeypatch):
    _use_catalog_settings(monkeypatch, ttl_seconds=0.05)
    calls = []

    def amazon(q):
        calls.append(q)
        return [_real()]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    asyncio.run(search_service.search_all("iphone 15"))
    search_service.clear_search_cache()
    time.sleep(0.07)  # older than the freshness window -> must re-scrape
    asyncio.run(search_service.search_all("iphone 15"))

    assert calls == ["iphone 15", "iphone 15"]


def test_stored_freshness_cap_bounds_serving(monkeypatch):
    _use_catalog_settings(monkeypatch, ttl_seconds=3600.0,
                          stored_freshness_seconds=0.05)
    calls = []

    def amazon(q):
        calls.append(q)
        return [_real()]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    asyncio.run(search_service.search_all("iphone 15"))
    search_service.clear_search_cache()
    time.sleep(0.07)  # cap (stored freshness) is sharper than the cache TTL
    asyncio.run(search_service.search_all("iphone 15"))

    assert calls == ["iphone 15", "iphone 15"]


def test_empty_search_is_never_persisted(monkeypatch):
    _use_catalog_settings(monkeypatch)
    _stub_others_empty(monkeypatch)
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [])

    assert asyncio.run(search_service.search_all("iphone 15")) == []
    # Honest empty is NOT stored: the next call must still run the live pipeline.
    assert get_store().search_offers("iphone 15") is None


def test_unpriced_or_keyless_offers_never_persisted_via_search(monkeypatch):
    """
    A source returning only unpriced/keyless placeholders ("Check price" rows)
    is non-empty for the response pipeline but contains NO valid comparable
    offers: nothing may be persisted to the catalog either.
    """
    _use_catalog_settings(monkeypatch)
    junk = [
        {**_real(), "product_key": ""},        # keyless
        {**_real(), "price_value": None},      # unpriced placeholder
    ]
    monkeypatch.setattr(search_service, "search_amazon", lambda q: junk)
    _stub_others_empty(monkeypatch)

    result = asyncio.run(search_service.search_all("iphone 15"))

    assert result == junk  # response layer still sees them (aggregator filters)
    assert get_store().search_offers("iphone 15") is None
    assert get_store().counts()["products"] == 0
    assert get_store().counts()["offers"] == 0


def test_stored_serving_does_not_leak_between_queries(monkeypatch):
    _use_catalog_settings(monkeypatch)
    seen = []

    def amazon(q):
        seen.append(q)
        return [_real(price=79999.0 if q == "iphone 15" else 399.0)]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    first = asyncio.run(search_service.search_all("iphone 15"))
    search_service.clear_search_cache()
    second = asyncio.run(search_service.search_all("tshirt"))

    assert first == [_real()]
    assert second == [_real(price=399.0)]  # different query -> scraped fresh
    assert seen == ["iphone 15", "tshirt"]