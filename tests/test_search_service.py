import asyncio

from app.services import search_service


def test_search_all_returns_only_real_scraper_results(monkeypatch, make_product):
    real = make_product()
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [real])
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])

    products = asyncio.run(search_service.search_all("iphone 15"))

    assert products == [real]
    assert all(p["platform"] == "Amazon" for p in products)


def test_search_all_returns_empty_when_every_platform_is_empty(monkeypatch):
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [])
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])

    assert asyncio.run(search_service.search_all("iphone 15")) == []


def test_search_forwards_query_verbatim_to_every_scraper(monkeypatch):
    received = []

    def recorder(name):
        def _scrape(q):
            received.append((name, q))
            return []
        return _scrape

    monkeypatch.setattr(search_service, "search_amazon", recorder("amazon"))
    monkeypatch.setattr(search_service, "search_flipkart", recorder("flipkart"))
    monkeypatch.setattr(search_service, "search_myntra", recorder("myntra"))
    monkeypatch.setattr(search_service, "search_ajio", recorder("ajio"))

    asyncio.run(search_service.search_all("  samsung galaxy s24  "))

    # Every scraper must receive the exact same query string.
    assert sorted(received) == [
        ("ajio", "  samsung galaxy s24  "),
        ("amazon", "  samsung galaxy s24  "),
        ("flipkart", "  samsung galaxy s24  "),
        ("myntra", "  samsung galaxy s24  "),
    ]


def test_search_concatenates_platform_results_in_order(monkeypatch, make_product):
    amazon_hits = [make_product(platform="Amazon", title="A1"), make_product(platform="Amazon", title="A2")]
    flipkart_hits = [make_product(platform="Flipkart", title="F1")]
    myntra_hits = [make_product(platform="Myntra", title="M1")]
    ajio_hits = [make_product(platform="Ajio", title="J1")]

    monkeypatch.setattr(search_service, "search_amazon", lambda q: amazon_hits)
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: flipkart_hits)
    monkeypatch.setattr(search_service, "search_myntra", lambda q: myntra_hits)
    monkeypatch.setattr(search_service, "search_ajio", lambda q: ajio_hits)

    products = asyncio.run(search_service.search_all("q"))

    assert [p["title"] for p in products] == ["A1", "A2", "F1", "M1", "J1"]


def test_search_one_source_failing_doesnt_kill_others(monkeypatch, make_product):
    """Error isolation: if Flipkart raises, the other sources still return."""
    def boom(q):
        raise RuntimeError("Flipkart is down")

    monkeypatch.setattr(search_service, "search_amazon", lambda q: [make_product(platform="Amazon")])
    monkeypatch.setattr(search_service, "search_flipkart", boom)
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])

    products = asyncio.run(search_service.search_all("test"))

    assert len(products) == 1
    assert products[0]["platform"] == "Amazon"
