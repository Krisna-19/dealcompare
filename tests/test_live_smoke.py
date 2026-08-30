"""
Live smoke test — NOT part of the deterministic suite.

pytest.ini deselects `live`-marked tests by default. Run explicitly with:

    pytest -m live

This hits the real Amazon storefront through the real scraper pipeline.
"""
import pytest

from app.services.search_service import search_all


@pytest.mark.live
def test_live_amazon_search_returns_real_shaped_products():
    import asyncio

    products = asyncio.run(search_all("iphone 15"))

    assert isinstance(products, list)
    for p in products:
        assert isinstance(p, dict)
        assert isinstance(p.get("title"), str) and p["title"].strip()
        assert p.get("price_value", 0) >= 0
        assert str(p.get("url", "")).startswith("https://")


@pytest.mark.live
def test_live_myntra_search_returns_real_shaped_products():
    """
    Live check that the real Myntra scraper returns genuine, non-hardcoded
    offers over the browser pipeline.  Myntra may legitimately return no
    results for a query (JS not rendered / blocked in some environments);
    in that case we only assert the honest-empty contract, not fabricated
    data.
    """
    from app.scrapers.myntra import search_myntra

    products = search_myntra("tshirt men")

    assert isinstance(products, list)
    for p in products:
        assert isinstance(p, dict)
        assert isinstance(p.get("title"), str) and p["title"].strip()
        assert p.get("platform") == "Myntra"
        # Every returned offer must be a real, Myntra-hosted, priced product.
        assert p.get("price_value", 0) > 0
        assert p.get("price_display") != "Check price"
        assert str(p.get("url", "")).startswith("https://www.myntra.com/")
