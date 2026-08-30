import requests
import pytest

from app.utils import http_client


@pytest.fixture(autouse=True)
def _fresh_settings_cache():
    """Env changes here must not leak into other tests via get_settings()."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_headers_use_configured_ua_and_language(monkeypatch):
    monkeypatch.setenv("USER_AGENT", "TestUA/9.0")
    monkeypatch.setenv("HTTP_ACCEPT_LANGUAGE", "en-GB,en;q=0.9")

    headers = http_client.get_headers()

    assert headers["User-Agent"] == "TestUA/9.0"
    assert headers["Accept-Language"] == "en-GB,en;q=0.9"


def test_http_user_agent_override_wins_over_base_user_agent(monkeypatch):
    monkeypatch.setenv("USER_AGENT", "BaseUA/1.0")
    monkeypatch.setenv("HTTP_USER_AGENT", "OverrideUA/2.0")

    assert http_client.get_headers()["User-Agent"] == "OverrideUA/2.0"


def test_session_mounts_retry_adapter_on_both_schemes(monkeypatch):
    monkeypatch.setenv("HTTP_MAX_RETRIES", "5")

    session = http_client.get_session()

    for prefix in ("http://", "https://"):
        adapter = session.get_adapter(prefix)
        assert adapter.max_retries.total == 5
        assert set(adapter.max_retries.status_forcelist) == {429, 500, 502, 503, 504}
        assert adapter.max_retries.allowed_methods == ["GET"]


def test_fetch_url_returns_body_only_on_http_200(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text

    class FakeSession:
        def __init__(self, response):
            self._response = response

        def get(self, url, **kwargs):
            return self._response

    ok = FakeSession(FakeResponse(200, "<html>ok</html>"))
    monkeypatch.setattr(http_client, "get_session", lambda: ok)
    assert http_client.fetch_url("https://example.com") == "<html>ok</html>"

    not_ok = FakeSession(FakeResponse(503, "busy"))
    monkeypatch.setattr(http_client, "get_session", lambda: not_ok)
    assert http_client.fetch_url("https://example.com") is None

    boom = FakeSession(None)
    monkeypatch.setattr(http_client, "get_session", lambda: boom)

    def raise_conn_error(*a, **kw):
        raise requests.exceptions.ConnectionError("refused")

    boom.get = raise_conn_error
    assert http_client.fetch_url("https://example.com") is None


def test_fetch_url_honors_explicit_timeout(monkeypatch):
    seen = {}

    class FakeSession:
        def get(self, url, **kwargs):
            seen["timeout"] = kwargs.get("timeout")
            resp = requests.Response()
            resp.status_code = 200
            resp._content = b"body"
            return resp

    monkeypatch.setattr(http_client, "get_session", lambda: FakeSession())

    http_client.fetch_url("https://example.com", timeout=3.5)

    assert seen["timeout"] == 3.5
