from pathlib import Path

from app.scrapers.amazon import build_search_url


def test_search_url_uses_query_verbatim():
    assert build_search_url("iphone 15") == "https://www.amazon.in/s?k=iphone+15"


def test_search_url_has_no_brand_prefix_or_category_facet():
    url = build_search_url("samsung galaxy s24")
    assert "apple+" not in url
    assert "rh=" not in url


SCRAPER_SOURCE = (
    Path(__file__).resolve().parents[1]
    .joinpath("app", "scrapers", "amazon.py")
    .read_text(encoding="utf-8")
)


def test_no_iphone15_hardcoding_remains_in_amazon_scraper():
    """Regression guard: the scraper must stay query-generic."""
    assert '"iphone 15"' not in SCRAPER_SOURCE
    assert "apple+" not in SCRAPER_SOURCE
    assert "1389401031" not in SCRAPER_SOURCE  # electronics category facet id
