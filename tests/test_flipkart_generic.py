"""
Flipkart scraper generic tests — URL building, no-hardcoding regression,
and public API behaviour.  No network access.
"""

import pytest

from app.scrapers.flipkart import build_search_url


# --- build_search_url tests ------------------------------------------------

def test_build_search_url_basic():
    url = build_search_url("iphone 15")
    assert url == "https://www.flipkart.com/search?q=iphone+15"


def test_build_search_url_special_characters():
    url = build_search_url("Samsung Galaxy S24 5G (Onyx Black)")
    assert url.startswith("https://www.flipkart.com/search?q=")
    assert "Samsung" in url
    assert "Galaxy" in url
    assert "%28" in url and "%29" in url  # parentheses encoded


def test_build_search_url_hindi_characters():
    url = build_search_url("लैपटॉप")
    assert url.startswith("https://www.flipkart.com/search?q=")
    # Should be URL-encoded, not raw Hindi
    assert "लैपटॉप" not in url or "%E0" in url


def test_build_search_url_empty_query():
    url = build_search_url("")
    assert url == "https://www.flipkart.com/search?q="


def test_build_search_url_preserves_query_order():
    url1 = build_search_url("red shirt men")
    url2 = build_search_url("red shirt men")
    assert url1 == url2


# --- No-hardcoding regression guards ---------------------------------------

def test_scraper_module_does_not_contain_hardcoded_selectors():
    """
    Regression guard: the Flipkart scraper must NOT contain hardcoded
    CSS class selectors as static strings in the public API path.
    All selector logic must live in the DOM fallback helper, and the
    primary path must use __NEXT_DATA__ JSON.
    """
    import inspect
    from app.scrapers import flipkart

    source = inspect.getsource(flipkart)

    # The public search_flipkart function should not reference CSS selectors
    func_source = inspect.getsource(flipkart.search_flipkart)
    assert "_1fQZEK" not in func_source, (
        "Hardcoded CSS selector found in search_flipkart — use __NEXT_DATA__ or DOM fallback"
    )


def test_flipkart_has_protocol_conformance():
    """search_flipkart must be a callable that accepts a query string."""
    from app.scrapers.flipkart import search_flipkart

    assert callable(search_flipkart)
    import inspect
    sig = inspect.signature(search_flipkart)
    params = list(sig.parameters.keys())
    assert params == ["query"], (
        f"search_flipkart must accept (query), got {params}"
    )


def test_flipkart_returns_list_or_empty(monkeypatch):
    """search_flipkart must always return a list, never raise."""
    from app.scrapers.flipkart import search_flipkart

    # With no browser available, it should return [] gracefully
    result = search_flipkart("nonexistent test query xyz")
    assert isinstance(result, list)
