"""
Deterministic cross-store contract test for Ajio.

Proves that an Ajio offer for the same SKU as an existing (Amazon/Flipkart)
offer is merged into that product's single card — NOT into a duplicate card —
and that best-offer selection, offer integrity, and card identity all hold
without any change to aggregation logic.  Ajio data here is mocked at the
search-service seam (the same way the other cross-store tests mock scrapers).
"""
from fastapi.testclient import TestClient

from app.main import app
from app.services import search_service

client = TestClient(app)


def test_ajio_offer_merges_into_existing_product_card(monkeypatch):
    """
    Same SKU across stores -> exactly ONE product card with offers from both
    Amazon and Ajio; best price picks the lowest; no fabricated platform.
    """
    # Amazon has the base S24.
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [
        {
            "title": "Samsung Galaxy S24 (Onyx Black, 128 GB)",
            "product_key": "samsung-s24-128gb",
            "platform": "Amazon",
            "price_value": 74999.0,
            "price_display": "\u20b974,999",
            "url": "https://www.amazon.in/dp/S24A",
            "image": "",
        }
    ])
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    # Ajio has the SAME base S24 SKU at a lower price.
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [
        {
            "title": "Samsung Galaxy S24 (Onyx Black, 128 GB)",
            "product_key": "samsung-s24-128gb",
            "platform": "Ajio",
            "price_value": 73999.0,
            "price_display": "\u20b973,999",
            "url": "https://www.ajio.com/samsung-galaxy-s24-5g-mobile/p/440001006",
            "image": "https://assets.ajio.com/img/s24.jpg",
        }
    ])

    res = client.get("/search", params={"query": "samsung galaxy s24"})

    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Products compared successfully"
    # Same SKU -> exactly ONE product card with two store offers.
    assert len(data["results"]) == 1
    group = data["results"][0]
    offers = group["offers"]

    assert sorted(o["platform"] for o in offers) == ["Ajio", "Amazon"]
    ajio_offer = next(o for o in offers if o["platform"] == "Ajio")
    assert ajio_offer["url"].startswith("https://www.ajio.com/")
    assert ajio_offer["price_value"] == 73999.0
    assert ajio_offer["price_display"] == "\u20b973,999"
    assert ajio_offer["image"]

    # Card identity is unchanged (title from the first/best representative).
    assert group["title"] == "Samsung Galaxy S24 (Onyx Black, 128 GB)"
    # Best-offer logic still works: Ajio is now the cheapest cross-store.
    assert group["best_price"] == "\u20b973,999"
    assert group["best_platform"] == "Ajio"
    amazon_offer = next(o for o in offers if o["platform"] == "Amazon")
    assert amazon_offer["price_value"] == 74999.0


def test_ajio_only_result_forms_its_own_card(monkeypatch):
    """
    When only Ajio returns a result, it must form its own valid card with
    exactly that offer and honest Ajio data — no fabricated platform.
    """
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [])
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [
        {
            "title": "Samsung Galaxy S24 (Onyx Black, 128 GB)",
            "product_key": "samsung-s24-128gb",
            "platform": "Ajio",
            "price_value": 73999.0,
            "price_display": "\u20b973,999",
            "url": "https://www.ajio.com/samsung-galaxy-s24-5g-mobile/p/440001006",
            "image": "https://assets.ajio.com/img/s24.jpg",
        }
    ])

    res = client.get("/search", params={"query": "samsung galaxy s24"})

    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 1
    group = data["results"][0]
    assert group["best_platform"] == "Ajio"
    assert group["best_price"] == "\u20b973,999"
    offers = group["offers"]
    assert len(offers) == 1 and offers[0]["platform"] == "Ajio"
