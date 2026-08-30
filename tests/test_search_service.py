import asyncio
import time

from app.services import search_service


def test_search_all_returns_only_real_scraper_results(monkeypatch, make_product):
    real = make_product()
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [real])
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])

    products = asyncio.run(search_service.search_all("iphone 15"))

    assert products == [real]
    assert all(p["platform"] == "Amazon" for p in products)


def test_search_all_returns_empty_when_every_platform_is_empty(monkeypatch):
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [])
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])

    assert asyncio.run(search_service.search_all("iphone 15")) == []


def test_search_forwards_query_verbatim_to_every_scraper(monkeypatch):
    received = []

    def recorder(name):
        def _scrape(q):
            received.append((name, q))
            return []
        return _scrape

    monkeypatch.setattr(search_service, "search_amazon", recorder("amazon"))
    monkeypatch.setattr(search_service, "search_flipkart", recorder("flipkart"))
    monkeypatch.setattr(search_service, "search_myntra", recorder("myntra"))
    monkeypatch.setattr(search_service, "search_ajio", recorder("ajio"))

    asyncio.run(search_service.search_all("  samsung galaxy s24  "))

    # Every scraper must receive the exact same query string.
    assert sorted(received) == [
        ("ajio", "  samsung galaxy s24  "),
        ("amazon", "  samsung galaxy s24  "),
        ("flipkart", "  samsung galaxy s24  "),
        ("myntra", "  samsung galaxy s24  "),
    ]


def test_search_concatenates_platform_results_in_order(monkeypatch, make_product):
    amazon_hits = [make_product(platform="Amazon", title="A1"), make_product(platform="Amazon", title="A2")]
    flipkart_hits = [make_product(platform="Flipkart", title="F1")]
    myntra_hits = [make_product(platform="Myntra", title="M1")]
    ajio_hits = [make_product(platform="Ajio", title="J1")]

    monkeypatch.setattr(search_service, "search_amazon", lambda q: amazon_hits)
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: flipkart_hits)
    monkeypatch.setattr(search_service, "search_myntra", lambda q: myntra_hits)
    monkeypatch.setattr(search_service, "search_ajio", lambda q: ajio_hits)

    products = asyncio.run(search_service.search_all("q"))

    assert [p["title"] for p in products] == ["A1", "A2", "F1", "M1", "J1"]


def test_search_one_source_failing_doesnt_kill_others(monkeypatch, make_product):
    """Error isolation: if Flipkart raises, the other sources still return."""
    def boom(q):
        raise RuntimeError("Flipkart is down")

    monkeypatch.setattr(search_service, "search_amazon", lambda q: [make_product(platform="Amazon")])
    monkeypatch.setattr(search_service, "search_flipkart", boom)
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])

    products = asyncio.run(search_service.search_all("test"))

    assert len(products) == 1
    assert products[0]["platform"] == "Amazon"


# ---------------------------------------------------------------------------
# Search response cache.
# ---------------------------------------------------------------------------

class _CacheSettings:
    """Tiny stand-in for app.core.config.Settings so tests control the cache."""

    def __init__(self, enabled=True, ttl_seconds=3600.0):
        self.search_cache_enabled = enabled
        self.search_cache_ttl_seconds = ttl_seconds


def _stub_others_empty(monkeypatch):
    """Stub the three non-Amazon scrapers to return nothing (Amazon is
    configured per-test by the caller)."""
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])


def test_cache_first_request_performs_the_search(monkeypatch, make_product):
    calls = []
    real = make_product()

    def amazon(q):
        calls.append(q)
        return [real]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    result = asyncio.run(search_service.search_all("iphone 15"))

    assert result == [real]
    assert calls == ["iphone 15"]


def test_cache_repeated_identical_query_uses_cache(monkeypatch, make_product):
    calls = []
    real = make_product()

    def amazon(q):
        calls.append(q)
        return [real]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    first = asyncio.run(search_service.search_all("iphone 15"))
    second = asyncio.run(search_service.search_all("iphone 15"))

    assert first == [real]
    assert second == [real]
    assert calls == ["iphone 15"]  # scraped once, second call served from cache


def test_cache_normalized_equivalent_queries_share_entry(monkeypatch, make_product):
    calls = []
    real = make_product()

    def amazon(q):
        calls.append(q)
        return [real]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    first = asyncio.run(search_service.search_all("  iPhone   15 "))
    second = asyncio.run(search_service.search_all("iphone 15"))

    assert first == [real]
    assert second == [real]
    # Both queries normalize to the same key -> single scrape, second is a hit.
    assert calls == ["  iPhone   15 "]


def test_cache_expired_entry_triggers_fresh_search(monkeypatch, make_product):
    monkeypatch.setattr(
        search_service, "get_settings", lambda: _CacheSettings(ttl_seconds=0.05)
    )
    calls = []
    real = make_product()

    def amazon(q):
        calls.append(q)
        return [real]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    asyncio.run(search_service.search_all("iphone 15"))
    time.sleep(0.07)  # let the entry expire
    asyncio.run(search_service.search_all("iphone 15"))

    assert calls == ["iphone 15", "iphone 15"]


def test_cache_failed_search_is_not_cached(monkeypatch, make_product):
    calls = []

    def boom(q):
        calls.append("boom")
        raise RuntimeError("Amazon down")

    monkeypatch.setattr(search_service, "search_amazon", boom)
    _stub_others_empty(monkeypatch)

    # All sources "fail" -> honest empty, which is never cached.
    assert asyncio.run(search_service.search_all("iphone 15")) == []

    # The earlier failure must not be served from cache: a fresh search runs
    # and now returns the recovered results.
    real = make_product()
    monkeypatch.setattr(search_service, "search_amazon", lambda q: calls.append("ok") or [real])

    second = asyncio.run(search_service.search_all("iphone 15"))

    assert second == [real]
    assert calls == ["boom", "ok"]


def test_cache_empty_results_are_not_cached(monkeypatch):
    calls = []
    _stub_others_empty(monkeypatch)
    monkeypatch.setattr(search_service, "search_amazon", lambda q: calls.append(q) or [])

    assert asyncio.run(search_service.search_all("iphone 15")) == []
    assert asyncio.run(search_service.search_all("iphone 15")) == []

    assert calls == ["iphone 15", "iphone 15"]


def test_cache_disabled_bypasses_cache(monkeypatch, make_product):
    monkeypatch.setattr(
        search_service, "get_settings", lambda: _CacheSettings(enabled=False)
    )

    calls = []
    real = make_product()

    def amazon(q):
        calls.append(q)
        return [real]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    asyncio.run(search_service.search_all("iphone 15"))
    asyncio.run(search_service.search_all("iphone 15"))

    assert calls == ["iphone 15", "iphone 15"]
