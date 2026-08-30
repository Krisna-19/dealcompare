import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Starlette's ServerErrorMiddleware sends the registered Exception-handler
# response but still re-raises internally; this client surfaces only responses.
quiet_client = TestClient(app, raise_server_exceptions=False)


def _product(platform, title, price_value):
    return {
        "title": title,
        "product_key": "apple-iphone-15-128gb",
        "platform": platform,
        "price_value": price_value,
        "price_display": f"\u20b9{price_value}",
        "url": f"https://example.com/{platform.lower()}/{price_value}",
        "image": "https://example.com/img.jpg",
    }


def _fake_search(products):
    async def _search(q):
        return products

    return _search


@pytest.fixture
def sample_products():
    return [
        _product("Amazon", "iPhone 15 128GB", 79900),
        _product("Amazon", "Apple iPhone 15 (128 GB)", 80500),
    ]


# --- Success ---------------------------------------------------------------

def test_success_returns_200_with_exact_contract(sample_products, monkeypatch):
    monkeypatch.setattr("app.main.search_all", _fake_search(sample_products))

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"message", "results"}
    assert body["message"] == "Products compared successfully"
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 1  # two near-duplicates -> one group
    offer_keys = set(body["results"][0].keys())
    assert offer_keys == {"title", "best_price", "best_platform", "best_url", "offers"}


# --- Honest empty ----------------------------------------------------------

def test_empty_results_are_honest_200_not_error(monkeypatch):
    monkeypatch.setattr("app.main.search_all", _fake_search([]))

    res = client.get("/search", params={"query": "unobtainium widget xyz"})

    assert res.status_code == 200
    assert res.json() == {"message": "No products found", "results": []}


# --- Invalid input ---------------------------------------------------------

def test_missing_query_parameter_is_422():
    res = client.get("/search")

    assert res.status_code == 422


def test_missing_query_422_has_standard_detail_contract():
    res = client.get("/search")

    body = res.json()
    assert "detail" in body
    detail = body["detail"]
    assert isinstance(detail, list)
    assert len(detail) >= 1
    first_error = detail[0]
    assert "loc" in first_error
    assert "msg" in first_error


def test_blank_query_is_422_invalid_query():
    res = client.get("/search", params={"query": ""})

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["error"] == "invalid_query"
    assert "query" in detail["message"].lower()


def test_whitespace_only_query_is_422_invalid_query():
    res = client.get("/search", params={"query": "   \t "})

    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "invalid_query"


# --- Scraper / upstream failure -------------------------------------------

def test_upstream_failure_is_502_and_leaks_nothing(monkeypatch):
    def boom(q):
        raise RuntimeError(
            "playwright chromium crashed: C:\\Users\\secret\\browser\\path"
        )

    monkeypatch.setattr("app.main.search_all", boom)

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 502
    detail = res.json()["detail"]
    assert detail["error"] == "upstream_scrape_failed"
    assert isinstance(detail["message"], str) and len(detail["message"]) > 0
    # No internals leaked into the response.
    assert "playwright" not in res.text.lower()
    assert "chromium" not in res.text.lower()
    assert "secret" not in res.text.lower()
    assert res.json() != {"error": "anything"}  # old flat shape gone


def test_upstream_failure_never_returns_fake_success(monkeypatch):
    def boom(q):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.main.search_all", boom)

    res = client.get("/search", params={"query": "iphone 15"})

    body = res.json()
    assert res.status_code == 502
    detail = body["detail"]
    assert isinstance(detail, dict)
    assert detail["error"] == "upstream_scrape_failed"
    assert "results" not in detail
    assert "message" not in body


# --- Unexpected internal exceptions ---------------------------------------

def test_aggregation_crash_is_500_internal_error_without_leak(monkeypatch, sample_products):
    monkeypatch.setattr("app.main.search_all", _fake_search(sample_products))

    def broken_aggregate(products):
        raise ValueError("internal db credentials leaked-here")

    monkeypatch.setattr("app.main.aggregate_products", broken_aggregate)

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 500
    detail = res.json()["detail"]
    assert detail["error"] == "internal_error"
    assert isinstance(detail["message"], str) and len(detail["message"]) > 0
    assert "leaked-here" not in res.text
    assert "ValueError" not in res.text


def test_global_handler_catches_exceptions_escaping_endpoints():
    """Any exception escaping an endpoint must become a generic 500."""
    added_route = None

    @app.get("/__test_boom")
    async def boom():  # pragma: no cover - exercised via TestClient below
        raise RuntimeError("ultra-secret-stack-detail")

    added_route = app.routes[-1]
    try:
        res = quiet_client.get("/__test_boom")

        assert res.status_code == 500
        detail = res.json()["detail"]
        assert detail["error"] == "internal_error"
        assert detail["message"] == "An unexpected internal error occurred."
        assert "ultra-secret" not in res.text
    finally:
        app.routes.remove(added_route)
