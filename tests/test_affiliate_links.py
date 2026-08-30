from affiliates.amazon_links import build_amazon_search_link


def test_default_link_shape_and_tag():
    link = build_amazon_search_link("iphone 15")

    assert link == (
        "https://www.amazon.in/s?k=iphone+15&tag=dealcompare19-21"
    )


def test_query_is_url_encoded_with_plus_separators():
    link = build_amazon_search_link("Samsung Galaxy S24 Ultra 256GB")

    assert "k=Samsung+Galaxy+S24+Ultra+256GB" in link
    assert link.startswith("https://www.amazon.in/s?k=")


def test_trailing_slash_in_affiliate_base_url_does_not_duplicate(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("AFFILIATE_BASE_URL", "https://www.amazon.in/")
    get_settings.cache_clear()

    try:
        link = build_amazon_search_link("pixel 8")
        assert "//s?" not in link
        assert link == "https://www.amazon.in/s?k=pixel+8&tag=dealcompare19-21"
    finally:
        get_settings.cache_clear()
