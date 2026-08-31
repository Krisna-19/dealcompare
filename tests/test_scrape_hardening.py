"""
Production hardening in app/services/search_service.py:

  - scrape_concurrency_limit caps simultaneous scraper sessions globally.
  - source_timeout_seconds abandons a stalled marketplace (honest empty for
    that source) instead of stalling the whole /search pipeline.
"""

import asyncio
import threading
import time

from app.services import search_service


class _HardenedSettings:
    """Stand-in for app.core.config.Settings exposing just what we control."""

    def __init__(
        self,
        concurrency=2,
        timeout=60.0,
        cache_enabled=True,
        ttl_seconds=300.0,
    ):
        self.scrape_concurrency_limit = concurrency
        self.source_timeout_seconds = timeout
        self.search_cache_enabled = cache_enabled
        self.search_cache_ttl_seconds = ttl_seconds


def _stub_all(monkeypatch, make_product):
    real = make_product()
    monkeypatch.setattr(search_service, "get_settings", lambda: _HardenedSettings())
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [real])
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])


def test_search_all_still_returns_results_under_hardening(monkeypatch, make_product):
    _stub_all(monkeypatch, make_product)

    products = asyncio.run(search_service.search_all("iphone 15"))

    assert products == [make_product()]
    assert all(p["platform"] == "Amazon" for p in products)


def test_search_caps_global_concurrent_scrape_sessions(monkeypatch):
    active = 0
    peak = 0
    gate = threading.Lock()

    def tracker(_name):
        def _scrape(_q):
            nonlocal active, peak
            with gate:
                active += 1
                peak = max(peak, active)
            time.sleep(0.1)
            with gate:
                active -= 1
            return []

        return _scrape

    monkeypatch.setattr(
        search_service, "get_settings", lambda: _HardenedSettings(concurrency=2)
    )
    monkeypatch.setattr(search_service, "search_amazon", tracker("amazon"))
    monkeypatch.setattr(search_service, "search_flipkart", tracker("flipkart"))
    monkeypatch.setattr(search_service, "search_myntra", tracker("myntra"))
    monkeypatch.setattr(search_service, "search_ajio", tracker("ajio"))

    asyncio.run(search_service.search_all("q"))

    # Never more than the configured cap of browser sessions in flight.
    assert peak <= 2
    assert peak >= 1


def test_stalled_source_is_abandoned_not_stalling_the_response(
    monkeypatch, make_product
):
    """One hung scraper must neither stall /search nor corrupt its results."""
    real = make_product()
    unblock = threading.Event()

    def hang(_q):
        unblock.wait(10)  # far longer than the configured timeout
        return []

    monkeypatch.setattr(
        search_service,
        "get_settings",
        lambda: _HardenedSettings(concurrency=4, timeout=0.05),
    )
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [real])
    monkeypatch.setattr(search_service, "search_flipkart", hang)
    monkeypatch.setattr(search_service, "search_myntra", hang)
    monkeypatch.setattr(search_service, "search_ajio", hang)

    loop = asyncio.new_event_loop()
    try:
        started = time.monotonic()
        products = loop.run_until_complete(search_service.search_all("q"))
        elapsed = time.monotonic() - started
    finally:
        # Let the abandoned worker threads retire so nothing lingers.
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for t in pending:
            t.cancel()
        unblock.set()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    # Honest results from the healthy source, abandoned hung ones -> [].
    assert products == [real]
    assert elapsed < 2.0