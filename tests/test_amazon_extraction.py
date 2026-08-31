from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app.core.config import get_settings
from app.scrapers.amazon import extract_product_details

FIXTURES = Path(__file__).parent / "fixtures"

CURRENT_LAYOUT_HTML = (FIXTURES / "amazon_item_current_layout.html").read_text(
    encoding="utf-8"
)

LEGACY_LAYOUT_HTML = """
<div data-component-type="s-search-result">
  <h2>
    <a href="/dp/LEGACY123/ref=sr_1_5">
      <span>Legacy Layout Samsung Galaxy S24 256GB Smartphone</span>
    </a>
  </h2>
  <span class="a-price"><span class="a-offscreen">₹65,000</span></span>
  <img class="s-image" src="https://example.com/legacy.jpg">
</div>
"""

NO_TITLE_HTML = """
<div data-component-type="s-search-result">
  <span class="a-color-secondary">Something unrelated</span>
</div>
"""

NO_PRICE_HTML = """
<div data-component-type="s-search-result">
  <a class="a-link-normal s-line-clamp-2" href="/dp/NOPRICE9/ref=sr_1_2">
    <h2><span>Sony WH-1000XM5 Wireless Headphones with Mic</span></h2>
  </a>
</div>
"""


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser.new_page()
        browser.close()


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Env-var tests mutate settings; never leak cache across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _items(page, html):
    page.set_content(f"<html><body>{html}</body></html>")
    return page.query_selector_all('div[data-component-type="s-search-result"]')


def test_current_layout_extracts_all_fields(page):
    (item,) = _items(page, CURRENT_LAYOUT_HTML)

    details = extract_product_details(item)

    assert details is not None
    assert details["title"].startswith("iPhone 16e 128 GB")
    # Sponsored items carry a /sspa/click redirect wrapping the encoded
    # /dp/<ASIN> path; the scraper preserves it and Amazon resolves it.
    assert details["product_url"].startswith("https://www.amazon.in")
    assert "B0DXQH1DBS" in details["product_url"]
    assert details["price_value"] == 59900.0
    assert details["price_display"] == "₹59900"
    assert details["image"].startswith("https://m.media-amazon.com/images/I/")


def test_legacy_layout_still_supported(page):
    (item,) = _items(page, LEGACY_LAYOUT_HTML)

    details = extract_product_details(item)

    assert details is not None
    assert details["title"] == "Legacy Layout Samsung Galaxy S24 256GB Smartphone"
    assert details["product_url"] == "https://www.amazon.in/dp/LEGACY123/ref=sr_1_5"
    assert details["price_value"] == 65000.0


def test_item_without_title_or_link_is_skipped(page):
    (item,) = _items(page, NO_TITLE_HTML)

    assert extract_product_details(item) is None


def test_missing_price_keeps_historical_contract(page):
    (item,) = _items(page, NO_PRICE_HTML)

    details = extract_product_details(item)

    assert details is not None
    assert details["title"].startswith("Sony WH-1000XM5")
    assert details["price_value"] == 0
    assert details["price_display"] == "Check price"


def test_garbage_price_text_does_not_crash(page):
    html = NO_PRICE_HTML.replace(
        'href="/dp/NOPRICE9/ref=sr_1_2"', 'href="/dp/GARBAGE7/ref=sr_1_3"'
    ).replace(
        "</a>", "</a>"
        '<div><span class="a-offscreen">Free delivery</span></div>'
    )
    (item,) = _items(page, html)

    details = extract_product_details(item)

    assert details is not None
    assert details["price_value"] == 0
    assert details["price_display"] == "Check price"


def test_multiple_items_are_extracted_independently(page):
    """No state may leak between consecutive item parses."""
    items = _items(
        page,
        f"<div>{CURRENT_LAYOUT_HTML}</div><div>{LEGACY_LAYOUT_HTML}</div>",
    )
    assert len(items) == 2

    first = extract_product_details(items[0])
    second = extract_product_details(items[1])

    assert first is not None and second is not None
    assert first["title"].startswith("iPhone 16e 128 GB")
    assert second["title"] == "Legacy Layout Samsung Galaxy S24 256GB Smartphone"
    assert "B0DXQH1DBS" in first["product_url"]
    assert "LEGACY123" in second["product_url"]
    assert first["price_value"] == 59900.0
    assert second["price_value"] == 65000.0


def test_no_cost_emi_prose_before_real_price_is_ignored(page):
    """A prose a-offscreen snippet appearing BEFORE the price must not win."""
    html = """
    <div data-component-type="s-search-result">
      <a class="a-link-normal s-line-clamp-2" href="/dp/EMI123/ref=sr_1_1">
        <h2><span>Real Pro X 5G Smartphone</span></h2>
      </a>
      <span class="a-offscreen">Save extra with No Cost EMI</span>
      <span class="a-price"><span class="a-offscreen">₹42,999</span></span>
    </div>
    """
    (item,) = _items(page, html)

    details = extract_product_details(item)

    assert details is not None
    assert details["price_value"] == 42999.0
    assert details["price_display"] == "₹42999"


def test_emi_amount_copy_is_rejected_not_misread_as_price(page):
    """'EMI ₹4,999/month' must never become the product price."""
    html = NO_PRICE_HTML.replace(
        'href="/dp/NOPRICE9/ref=sr_1_2"', 'href="/dp/EMI999X/ref=sr_1_4"'
    ).replace(
        "</a>",
        "</a><div><span class=\"a-offscreen\">EMI ₹4,999/month</span></div>",
    )
    (item,) = _items(page, html)

    details = extract_product_details(item)

    assert details is not None
    assert details["price_value"] == 0
    assert details["price_display"] == "Check price"


def test_product_url_uses_configured_base_url(page, monkeypatch):
    monkeypatch.setenv("AMAZON_BASE_URL", "https://amazon.example.test")
    (item,) = _items(page, NO_PRICE_HTML)

    details = extract_product_details(item)

    assert details is not None
    assert (
        details["product_url"]
        == "https://amazon.example.test/dp/NOPRICE9/ref=sr_1_2"
    )


def test_absolute_href_preserved_unchanged(page, monkeypatch):
    monkeypatch.setenv("AMAZON_BASE_URL", "https://amazon.example.test")
    html = NO_PRICE_HTML.replace(
        'href="/dp/NOPRICE9/ref=sr_1_2"',
        'href="https://www.amazon.in/dp/NOPRICE9/ref=sr_1_2"',
    )
    (item,) = _items(page, html)

    details = extract_product_details(item)

    assert details is not None
    assert details["product_url"] == "https://www.amazon.in/dp/NOPRICE9/ref=sr_1_2"
