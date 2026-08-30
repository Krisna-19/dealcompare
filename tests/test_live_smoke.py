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


@pytest.mark.live
def test_ajio_fixture_dom_extraction_reads_real_markup():
    """
    Evaluate Ajio's `_EXTRACT_PRODUCTS_JS` against the local fixture HTML
    using a real (local-only) Playwright browser — no network to Ajio.  This
    proves the extractor navigates real Ajio-style card markup and yields the
    raw records that `normalise_ajio_product` turns into offers.
    """
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from app.scrapers.ajio import _EXTRACT_PRODUCTS_JS, normalise_ajio_product

    fixture = (
        Path(__file__).resolve().parents[1]
        / "tests" / "fixtures" / "ajio_search_results.html"
    ).read_text(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(fixture)
        raw_products = page.evaluate(_EXTRACT_PRODUCTS_JS)
        browser.close()

    # 3 valid cards (phone, base case, ultra); the 2 malformed ones have no
    # product link / no price and must not surface as raw product anchors.
    assert isinstance(raw_products, list)

    normalised = []
    for raw in raw_products:
        item = normalise_ajio_product(raw, "samsung galaxy s24")
        if item is not None:
            normalised.append(item)

    # The 3 valid cards (base phone, base case, Ultra) all become normalised
    # Ajio offers at the scraper level; the 2 malformed cards (no link / no
    # usable price) never become offers.  Sub-variant relevance separation is
    # enforced downstream by filter_irrelevant_products, not in the scraper.
    titles = {n["title"] for n in normalised}
    assert len(normalised) == 3
    assert any("Galaxy S24 5G" in t for t in titles)
    assert any("S24 Back Case" in t for t in titles)
    assert any("S24 Ultra" in t for t in titles)
    assert all(n["platform"] == "Ajio" for n in normalised)
    assert all(n["url"].startswith("https://www.ajio.com/") for n in normalised)


@pytest.mark.live
def test_live_ajio_search_returns_honest_empty_contract():
    """
    Live check that the real Ajio scraper never fabricates data.  Ajio fronts
    its site with Akamai anti-bot and returns HTTP 403 to automated clients in
    this environment, so `search_ajio` is expected to return an honest empty
    list (not raise, not invent products).  If the site becomes reachable this
    should instead surface real, priced Ajio offers.
    """
    from app.scrapers.ajio import search_ajio

    products = search_ajio("samsung galaxy s24")

    assert isinstance(products, list)
    for p in products:
        assert isinstance(p, dict)
        assert isinstance(p.get("title"), str) and p["title"].strip()
        assert p.get("platform") == "Ajio"
        assert p.get("price_value", 0) > 0
        assert p.get("price_display") != "Check price"
        assert str(p.get("url", "")).startswith("https://www.ajio.com/")
