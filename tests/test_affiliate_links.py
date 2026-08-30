import pytest

from affiliates.amazon_links import (
    build_amazon_search_link,
    build_ajio_search_link,
    build_flipkart_search_link,
    build_myntra_search_link,
    _append_tag,
)


# ---------------------------------------------------------------------------
# Amazon (default tag always present)
# ---------------------------------------------------------------------------

def test_amazon_default_link_shape_and_tag():
    link = build_amazon_search_link("iphone 15")
    assert link == "https://www.amazon.in/s?k=iphone+15&tag=dealcompare19-21"


def test_amazon_query_is_url_encoded_with_plus_separators():
    link = build_amazon_search_link("Samsung Galaxy S24 Ultra 256GB")
    assert "k=Samsung+Galaxy+S24+Ultra+256GB" in link
    assert link.startswith("https://www.amazon.in/s?k=")


def test_amazon_trailing_slash_in_affiliate_base_url_does_not_duplicate(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("AFFILIATE_BASE_URL", "https://www.amazon.in/")
    get_settings.cache_clear()

    try:
        link = build_amazon_search_link("pixel 8")
        assert "//s?" not in link
        assert link == "https://www.amazon.in/s?k=pixel+8&tag=dealcompare19-21"
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Flipkart / Myntra / Ajio (tag opt-in; raw URL when tag unset)
# ---------------------------------------------------------------------------

def test_flipkart_link_with_configured_tag(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("FLIPKART_AFFILIATE_TAG", "fk-21")
    get_settings.cache_clear()

    try:
        link = build_flipkart_search_link("iphone 15")
        assert link == "https://www.flipkart.com/search?q=iphone+15&tag=fk-21"
    finally:
        get_settings.cache_clear()


def test_flipkart_link_raw_when_no_tag():
    assert build_flipkart_search_link("iphone 15") == (
        "https://www.flipkart.com/search?q=iphone+15"
    )


def test_myntra_link_with_configured_tag(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("MYNTRA_AFFILIATE_TAG", "my-21")
    get_settings.cache_clear()

    try:
        link = build_myntra_search_link("tshirt")
        assert link == "https://www.myntra.com/tshirt?tag=my-21"
    finally:
        get_settings.cache_clear()


def test_myntra_link_raw_when_no_tag():
    assert build_myntra_search_link("tshirt") == "https://www.myntra.com/tshirt"


def test_ajio_link_with_configured_tag(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("AJIO_AFFILIATE_TAG", "aj-21")
    get_settings.cache_clear()

    try:
        link = build_ajio_search_link("kurti")
        assert link == "https://www.ajio.com/search/kurti?tag=aj-21"
    finally:
        get_settings.cache_clear()


def test_ajio_link_raw_when_no_tag():
    assert build_ajio_search_link("kurti") == "https://www.ajio.com/search/kurti"


# ---------------------------------------------------------------------------
# _append_tag primitive
# ---------------------------------------------------------------------------

def test_append_tag_uses_question_mark_when_no_query_string():
    assert _append_tag("https://x.com/p", "t") == "https://x.com/p?tag=t"


def test_append_tag_uses_ampersand_when_query_string_exists():
    assert _append_tag("https://x.com/p?a=1", "t") == "https://x.com/p?a=1&tag=t"


def test_append_tag_empty_returns_url_unchanged():
    assert _append_tag("https://x.com/p", "") == "https://x.com/p"
