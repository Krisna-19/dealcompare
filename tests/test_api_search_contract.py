from fastapi.testclient import TestClient

from app.main import app
from app.services import search_service

client = TestClient(app)


def _mock_scrapers(monkeypatch, amazon_results):
    monkeypatch.setattr(search_service, "search_amazon", lambda q: amazon_results)
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])


def _offer(platform, title, price, image):
    return {
        "title": title,
        "product_key": "apple-iphone-15-128gb",
        "platform": platform,
        "price_value": price,
        "price_display": f"\u20b9{int(price):,}",
        "url": f"https://example.com/{platform.lower()}/{int(price)}",
        "image": image,
    }


def test_search_contract_with_real_results(monkeypatch):
    """
    iPhone-15 flow end-to-end with Amazon returning real results:
    grouping, best-offer selection and the response contract must hold,
    and no fabricated platform may appear.
    """
    _mock_scrapers(monkeypatch, [
        {
            "title": "Apple iPhone 15 (128 GB) - Black",
            "product_key": "apple-iphone-15-128gb",
            "platform": "Amazon",
            "price_value": 79999.0,
            "price_display": "\u20b979,999",
            "url": "https://www.amazon.in/dp/A",
            "image": "https://example.com/a.jpg",
        },
        {
            "title": "Apple iPhone 15 (128 GB) - Blue",
            "product_key": "apple-iphone-15-128gb",
            "platform": "Amazon",
            "price_value": 78499.0,
            "price_display": "\u20b978,499",
            "url": "https://www.amazon.in/dp/B",
        },
    ])

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Products compared successfully"

    # Black and Blue are distinct colour SKUs: two separate product cards,
    # each carrying only the offers for that exact colour.
    assert len(data["results"]) == 2
    by_title = {g["title"]: g for g in data["results"]}
    assert set(by_title) == {
        "Apple iPhone 15 (128 GB) - Black",
        "Apple iPhone 15 (128 GB) - Blue",
    }
    assert by_title["Apple iPhone 15 (128 GB) - Blue"]["best_price"] == "\u20b978,499"
    assert by_title["Apple iPhone 15 (128 GB) - Blue"]["best_url"] == "https://www.amazon.in/dp/B"
    assert by_title["Apple iPhone 15 (128 GB) - Black"]["best_price"] == "\u20b979,999"

    for group in data["results"]:
        offers = group["offers"]
        assert len(offers) == 1
        assert all(o["platform"] == "Amazon" for o in offers)
        assert all(o["price_value"] > 0 for o in offers)
        assert not any("Check price" == o.get("price_display") for o in offers)


def test_search_returns_honest_empty_result_without_fakes(monkeypatch):
    _mock_scrapers(monkeypatch, [])

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    assert res.json() == {
        "message": "No products found",
        "category": "Electronics",
        "results": [],
    }


def test_myntra_offers_aggregate_into_correct_card(monkeypatch):
    """
    When the real Myntra scraper returns an offer for the same SKU as an
    Amazon offer, it must be grouped into that product's single card (not
    create a duplicate card) and expose valid, Myntra-hosted offer data.
    """
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [
        {
            "title": "Samsung Galaxy S24 (Onyx Black, 128 GB)",
            "product_key": "samsung-galaxy-s24-onyx-black-128gb",
            "platform": "Amazon",
            "price_value": 74999.0,
            "price_display": "\u20b974,999",
            "url": "https://www.amazon.in/dp/S24A",
            "image": "",
        }
    ])
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [
        {
            "title": "Samsung Galaxy S24 (Onyx Black, 128 GB)",
            "product_key": "samsung-galaxy-s24-onyx-black-128gb",
            "platform": "Myntra",
            "price_value": 75999.0,
            "price_display": "\u20b975,999",
            "url": "https://www.myntra.com/samsung-galaxy-s24-onyx-black/45210973/buy",
            "image": "https://assets.myntassets.com/s24.jpg",
        }
    ])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])

    res = client.get("/search", params={"query": "samsung galaxy s24"})

    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Products compared successfully"
    # Same SKU -> exactly ONE product card, two store offers.
    assert len(data["results"]) == 1
    group = data["results"][0]
    offers = group["offers"]

    assert sorted(o["platform"] for o in offers) == ["Amazon", "Myntra"]
    myntra_offer = next(o for o in offers if o["platform"] == "Myntra")
    assert myntra_offer["url"].startswith("https://www.myntra.com/")
    assert myntra_offer["price_value"] == 75999.0
    assert myntra_offer["price_display"] == "\u20b975,999"
    assert myntra_offer["image"]  # Myntra image surfaced through the API

    # Cross-store best offer is chosen correctly across all stores.
    assert group["best_price"] == "\u20b974,999"
    assert group["best_platform"] == "Amazon"


def test_home_endpoint_reports_running_api():
    res = client.get("/")

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"message"}
    assert isinstance(body["message"], str)
    assert "DealCompare API running" in body["message"]


# --- Task 4: typed response contract --------------------------------------


def test_search_response_schema_is_exact(monkeypatch):
    """
    The full /search response must match the published schema exactly:
    top-level {message, category, results}; every card has
    {title, best_price, best_platform, best_url, image, offers}; every offer
    has {title, product_key, platform, price_value, price_display, url,
    image} with the documented types.  This pins the contract so the
    frontend can rely on it without guessing.
    """
    _mock_scrapers(monkeypatch, [
        _offer("Amazon", "Apple iPhone 15 (128 GB) - Black", 79999.0, "https://example.com/a.jpg"),
        _offer("Myntra", "Apple iPhone 15 (128 GB) - Blue", 78999.0, "https://example.com/b.jpg"),
    ])

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()

    assert set(data.keys()) == {"message", "category", "results"}
    assert data["message"] == "Products compared successfully"
    assert data["category"] == "Electronics"
    assert isinstance(data["results"], list) and data["results"]

    for card in data["results"]:
        assert set(card.keys()) == {
            "title", "best_price", "best_platform", "best_url", "image", "offers",
        }
        assert isinstance(card["title"], str) and card["title"]
        assert isinstance(card["best_price"], str) and card["best_price"]
        assert isinstance(card["best_platform"], str) and card["best_platform"]
        assert isinstance(card["best_url"], str) and card["best_url"]
        assert isinstance(card["image"], str)
        assert isinstance(card["offers"], list)

        for offer in card["offers"]:
            assert set(offer.keys()) == {
                "title", "product_key", "platform",
                "price_value", "price_display", "url", "image",
            }
            assert isinstance(offer["title"], str) and offer["title"]
            assert isinstance(offer["product_key"], str) and offer["product_key"]
            assert isinstance(offer["platform"], str) and offer["platform"]
            assert isinstance(offer["price_value"], (int, float)) and offer["price_value"] > 0
            assert isinstance(offer["price_display"], str) and offer["price_display"]
            assert isinstance(offer["url"], str) and offer["url"]
            assert isinstance(offer["image"], str)


def test_category_is_detected_and_echoed(monkeypatch):
    """
    The response 'category' field is driven by detect_category and is present
    even for an honest-empty result, matching what the UI expects.
    """
    cases = [
        ("tshirt men", "Fashion"),
        ("iphone 15", "Electronics"),
        ("serum for face", "Beauty"),
        ("samsung galaxy s24", "General"),
        ("random generic thing", "General"),
    ]
    for query, expected in cases:
        _mock_scrapers(monkeypatch, [])
        res = client.get("/search", params={"query": query})

        assert res.status_code == 200
        assert res.json()["category"] == expected


def test_card_image_uses_first_nonempty_offer_image(monkeypatch):
    """
    The card-level 'image' is the first non-empty offer image, so cards render
    an image without any client-side derivation.
    """
    _mock_scrapers(monkeypatch, [
        _offer("Amazon", "Apple iPhone 15 (128 GB) - Black", 79999.0, "https://example.com/first.jpg"),
        _offer("Myntra", "Apple iPhone 15 (128 GB) - Black", 78999.0, ""),
    ])

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    card = res.json()["results"][0]
    assert card["image"] == "https://example.com/first.jpg"


def test_card_image_falls_through_to_later_offer(monkeypatch):
    """
    When the first offer carries no image, the card image comes from the next
    non-empty offer image instead.
    """
    _mock_scrapers(monkeypatch, [
        _offer("Amazon", "Apple iPhone 15 (128 GB) - Black", 79999.0, ""),
        _offer("Myntra", "Apple iPhone 15 (128 GB) - Black", 78999.0, "https://example.com/later.jpg"),
    ])

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    card = res.json()["results"][0]
    assert card["image"] == "https://example.com/later.jpg"


def test_card_image_is_empty_when_no_offer_has_image(monkeypatch):
    """No offer image anywhere -> the card image is an empty string."""
    _mock_scrapers(monkeypatch, [
        _offer("Amazon", "Apple iPhone 15 (128 GB) - Black", 79999.0, ""),
        _offer("Myntra", "Apple iPhone 15 (128 GB) - Black", 78999.0, ""),
    ])

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    card = res.json()["results"][0]
    assert card["image"] == ""
