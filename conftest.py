import os
import sys

# Ensure the project root (containing the `app` package) is importable
# regardless of where pytest is invoked from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest


@pytest.fixture(autouse=True)
def _reset_search_cache(tmp_path, monkeypatch):
    """
    Fresh in-memory search cache and an isolated catalog store per test.

    Several suites reuse the same query string (e.g. "iphone 15") with
    different mocked scrapers; the search cache AND the persisted catalog
    must never leak a result from one test into another.  The catalog store
    is pointed at a per-test tmp dir and its singleton dropped, so the
    catalog-based "stored offers first" path is exercised in isolation.
    """
    from app.services.search_service import clear_search_cache
    from app.storage.store import reset_store

    monkeypatch.setenv("DEALCOMPARE_DATA_DIR", str(tmp_path / "catalog"))
    reset_store()
    clear_search_cache()
    yield
    reset_store()
    clear_search_cache()


@pytest.fixture
def make_product():
    """
    Factory building scraper-shaped product dicts for aggregation/API tests.

    All fields match what the Amazon scraper emits; overrides let tests
    exercise placeholder, missing-field and multi-product scenarios.
    """

    def _make(
        platform="Amazon",
        title="Apple iPhone 15 (128 GB) - Black",
        product_key="apple-iphone-15-128gb",
        price_value=79999.0,
        price_display="\u20b979,999",
        url=None,
        image=None,
        **extra,
    ):
        product = {
            "title": title,
            "product_key": product_key,
            "platform": platform,
            "price_value": price_value,
            "price_display": price_display,
            "url": url or f"https://www.example.com/{platform.lower()}/p",
            "image": image or "https://www.example.com/img.jpg",
        }
        product.update(extra)
        return product

    return _make
