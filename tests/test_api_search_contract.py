from fastapi.testclient import TestClient

from app.main import app
from app.services import search_service

client = TestClient(app)


def _mock_scrapers(monkeypatch, amazon_results):
    monkeypatch.setattr(search_service, "search_amazon", lambda q: amazon_results)
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])


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
    assert res.json() == {"message": "No products found", "results": []}


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
