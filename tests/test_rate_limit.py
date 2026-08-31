"""
Optional per-IP rate limiting (app/main.per_ip_rate_limit).

Off by default; every test here explicitly enables it via env vars so the
rest of the suite runs against the untouched default.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import _rate_limit_history, app
from app.core.config import get_settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """Tests mutate env + global middleware state; restore both afterwards."""
    get_settings.cache_clear()
    _rate_limit_history.clear()
    yield
    get_settings.cache_clear()
    _rate_limit_history.clear()


def _enable(monkeypatch, max_requests="3"):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", max_requests)
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()


def test_rate_limiter_disabled_by_default():
    for _ in range(10):
        res = client.get("/")
        assert res.status_code == 200
    assert not _rate_limit_history  # disabled limiter never records anything


def test_rate_limiter_allows_requests_up_to_limit(monkeypatch):
    _enable(monkeypatch, max_requests="3")

    for _ in range(3):
        res = client.get("/")
        assert res.status_code == 200


def test_rate_limiter_rejects_over_limit_with_standard_contract(monkeypatch):
    _enable(monkeypatch, max_requests="3")

    for _ in range(3):
        assert client.get("/").status_code == 200

    res = client.get("/")
    assert res.status_code == 429
    body = res.json()
    assert body["detail"]["error"] == "rate_limited"
    assert isinstance(body["detail"]["message"], str)
    assert len(body["detail"]["message"]) > 0
    assert "results" not in body
    assert "message" not in body


def test_rate_limiter_is_per_client_ip(monkeypatch):
    _enable(monkeypatch, max_requests="1")

    client_a = TestClient(app, client=("10.0.0.1", 12345))
    client_b = TestClient(app, client=("10.0.0.2", 54321))

    # IP A exhausts its single-request quota...
    assert client_a.get("/").status_code == 200
    assert client_a.get("/").status_code == 429
    # ...while IP B is completely unaffected.
    assert client_b.get("/").status_code == 200
    assert client_b.get("/").status_code == 429


def test_health_is_exempt_from_rate_limiter(monkeypatch):
    _enable(monkeypatch, max_requests="1")

    # The probe itself is never limited and consumes no quota.
    assert client.get("/health").status_code == 200

    # A real request uses the single-request quota...
    assert client.get("/").status_code == 200
    assert client.get("/").status_code == 429

    # ...and health stays available regardless.
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200