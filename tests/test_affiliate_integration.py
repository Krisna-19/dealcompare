from fastapi.testclient import TestClient

from app.main import app
from app.services import search_service

client = TestClient(app)


def _mock_all_platforms(monkeypatch, by_platform):
    monkeypatch.setattr(search_service, "search_amazon", lambda q: by_platform.get("Amazon", []))
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: by_platform.get("Flipkart", []))
    monkeypatch.setattr(search_service, "search_myntra", lambda q: by_platform.get("Myntra", []))
    monkeypatch.setattr(search_service, "search_ajio", lambda q: by_platform.get("Ajio", []))


def _amazon_offer(url="https://www.amazon.in/dp/ABC123", price=79999.0):
    return {
        "title": "Apple iPhone 15 (128 GB) - Black",
        "product_key": "apple-iphone-15-128gb",
        "platform": "Amazon",
        "price_value": price,
        "price_display": "\u20b979,999",
        "url": url,
        "image": "https://example.com/a.jpg",
    }


def test_amazon_offer_url_gains_default_affiliate_tag(monkeypatch):
    """
    Amazon has a default affiliate tag, so its offer URL at the /search
    boundary must carry the tag while grouping/card fields stay unchanged.
    """
    _mock_all_platforms(monkeypatch, {"Amazon": [_amazon_offer()]})

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Products compared successfully"
    assert len(data["results"]) == 1

    group = data["results"][0]
    assert group["title"] == "Apple iPhone 15 (128 GB) - Black"
    assert group["best_price"] == "\u20b979,999"
    assert group["best_platform"] == "Amazon"
    # The card-level best_url is untouched (computed on original urls).
    assert group["best_url"] == "https://www.amazon.in/dp/ABC123"

    offer = group["offers"][0]
    assert offer["platform"] == "Amazon"
    assert offer["url"] == "https://www.amazon.in/dp/ABC123?tag=dealcompare19-21"
    assert offer["price_value"] == 79999.0
    assert offer["title"] == "Apple iPhone 15 (128 GB) - Black"


def test_untagged_platform_url_stays_original(monkeypatch):
    """
    Myntra / Ajio / Flipkart have no default tag, so their offer urls must be
    returned verbatim (no fabricated tag, no change to the destination).
    """
    _mock_all_platforms(monkeypatch, {
        "Amazon": [_amazon_offer()],
        "Myntra": [{
            "title": "Apple iPhone 15 (128 GB) - Black",
            "product_key": "apple-iphone-15-128gb",
            "platform": "Myntra",
            "price_value": 81999.0,
            "price_display": "\u20b981,999",
            "url": "https://www.myntra.com/apple-iphone-15-128gb/123/buy",
            "image": "",
        }],
    })

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    group = data["results"][0]

    myntra_offer = next(o for o in group["offers"] if o["platform"] == "Myntra")
    assert myntra_offer["url"] == (
        "https://www.myntra.com/apple-iphone-15-128gb/123/buy"
    )

    amazon_offer = next(o for o in group["offers"] if o["platform"] == "Amazon")
    assert amazon_offer["url"] == "https://www.amazon.in/dp/ABC123?tag=dealcompare19-21"


def test_configured_custom_tag_applied(monkeypatch):
    """
    Setting the Ajio tag via env must append it to the Ajio offer url, and the
    change must not disturb the Amazon default or card grouping.
    """
    from app.core.config import get_settings

    monkeypatch.setenv("AJIO_AFFILIATE_TAG", "aj-cfg-21")
    get_settings.cache_clear()

    _mock_all_platforms(monkeypatch, {
        "Ajio": [{
            "title": "Apple iPhone 15 (128 GB) - Black",
            "product_key": "apple-iphone-15-128gb",
            "platform": "Ajio",
            "price_value": 78999.0,
            "price_display": "\u20b978,999",
            "url": "https://www.ajio.com/apple-iphone-15/p/123",
            "image": "",
        }],
    })

    try:
        res = client.get("/search", params={"query": "iphone 15"})
    finally:
        get_settings.cache_clear()

    assert res.status_code == 200
    data = res.json()
    group = data["results"][0]
    ajio_offer = next(o for o in group["offers"] if o["platform"] == "Ajio")
    assert ajio_offer["url"] == "https://www.ajio.com/apple-iphone-15/p/123?tag=aj-cfg-21"
