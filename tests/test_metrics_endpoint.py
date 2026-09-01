import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.metrics import metrics
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_metrics():
    """Fresh registry for every test: counters/gauges/histograms never leak."""
    metrics.reset()
    yield
    metrics.reset()


def _mock_all_scrapers(monkeypatch, return_values):
    """Point every registered marketplace scraper at fixed returns."""
    for source in ("amazon", "flipkart", "myntra", "ajio"):
        monkeypatch.setattr(
            f"app.services.search_service.search_{source}",
            lambda query, results=return_values: results,
        )


def test_metrics_returns_200_with_prometheus_format():
    metrics.gauge(
        "dc_build_info",
        "DealCompare API build information",
        1.0,
        {"version": app.version},
    )

    client.get("/health")
    res = client.get("/metrics")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")

    body = res.text
    assert "# TYPE dc_build_info gauge" in body
    assert 'dc_build_info{version="1.0"} 1' in body
    assert "# TYPE dc_http_requests_total counter" in body
    assert 'dc_http_requests_total{path="/health",status="200"} 1' in body
    assert "# TYPE dc_request_duration_seconds histogram" in body
    assert "dc_request_duration_seconds_bucket{path=\"/health\",status=\"200\",le=" in body
    assert "dc_request_duration_seconds_sum{path=\"/health\",status=\"200\"} " in body
    assert "dc_request_duration_seconds_count{path=\"/health\",status=\"200\"} 1" in body


def test_metrics_counts_search_outcomes(monkeypatch, make_product):
    # 1) Invalid query (blank) -> invalid_query, no scraping happens.
    res = client.get("/search", params={"query": "   "})
    assert res.status_code == 422

    # 2) Honest empty when every source finds nothing.
    _mock_all_scrapers(monkeypatch, [])
    res = client.get("/search", params={"query": "iphone 15"})
    assert res.status_code == 200
    assert res.json()["results"] == []

    # 3) Success with one real-shaped product.
    product = make_product()
    _mock_all_scrapers(monkeypatch, [product])
    res = client.get("/search", params={"query": "iphone 15"})
    assert res.status_code == 200
    assert len(res.json()["results"]) == 1

    body = client.get("/metrics").text
    assert 'dc_search_requests_total{outcome="invalid_query"} 1' in body
    assert 'dc_search_requests_total{outcome="empty"} 1' in body
    assert 'dc_search_requests_total{outcome="success"} 1' in body


def test_metrics_counters_are_relative_to_your_requests():
    client.get("/health")
    client.get("/health")
    client.get("/metrics")

    # The final GET renders its body BEFORE the middleware records it, so the
    # body reflects state up to (but not including) the read itself: /metrics
    # was hit exactly once by the time we render.
    body = client.get("/metrics").text
    assert 'dc_http_requests_total{path="/health",status="200"} 2' in body
    assert 'dc_http_requests_total{path="/metrics",status="200"} 1' in body


def test_metrics_is_exempt_from_rate_limiter(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "1")
    get_settings.cache_clear()
    try:
        for _ in range(3):
            res = client.get("/metrics")
            assert res.status_code == 200
    finally:
        get_settings.cache_clear()


def test_metrics_middleware_is_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "false")
    get_settings.cache_clear()
    try:
        client.get("/health")
        res = client.get("/metrics")
        assert res.status_code == 200
        assert "dc_http_requests_total" not in res.text
    finally:
        get_settings.cache_clear()