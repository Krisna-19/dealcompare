import pytest

from app.core.config import Settings, get_settings
from app.scrapers.amazon import build_search_url
from affiliates.amazon_links import build_amazon_search_link


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Tests may mutate env vars; ensure get_settings() reflects that."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_preserve_previous_hardcoded_values():
    s = Settings(_env_file=None)
    assert s.amazon_base_url == "https://www.amazon.in"
    assert s.user_agent == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    assert s.headless_browser is False
    assert s.page_load_timeout_ms == 60000
    assert s.selector_timeout_ms == 20000
    assert s.max_results_per_platform == 8
    assert s.match_score_threshold == 10
    assert s.http_max_retries == 3
    assert s.http_backoff_factor == 1.0
    assert s.http_timeout_seconds == 8.0
    assert s.group_similarity_threshold == 0.6
    assert s.amazon_affiliate_tag == "dealcompare19-21"
    assert s.allowed_origins_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://dealcompare.in",
    ]
    assert s.http_proxies_list == [None]


def test_env_overrides_apply(monkeypatch):
    monkeypatch.setenv("HEADLESS_BROWSER", "true")
    monkeypatch.setenv("MATCH_SCORE_THRESHOLD", "25")
    monkeypatch.setenv(
        "USER_AGENT", "TestAgent/1.0"
    )
    monkeypatch.setenv(
        "AMAZON_AFFILIATE_TAG", "testtag-21"
    )

    s = Settings(_env_file=None)
    assert s.headless_browser is True
    assert s.match_score_threshold == 25
    assert s.user_agent == "TestAgent/1.0"
    assert s.amazon_affiliate_tag == "testtag-21"


def test_csv_style_settings_parse_into_lists(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173, https://dealcompare.in ,"
    )
    monkeypatch.setenv(
        "HTTP_PROXIES", "http://10.0.0.1:8080,http://10.0.0.2:8080"
    )

    s = Settings(_env_file=None)
    assert s.allowed_origins_list == [
        "http://localhost:5173",
        "https://dealcompare.in",
    ]
    assert len(s.http_proxies_list) == 2


def test_build_search_url_uses_configured_base_url(monkeypatch):
    monkeypatch.setenv("AMAZON_BASE_URL", "https://example.com")
    assert build_search_url("iphone 15") == "https://example.com/s?k=iphone+15"


def test_affiliate_link_uses_configured_tag_and_base_url(monkeypatch):
    monkeypatch.setenv("AFFILIATE_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AMAZON_AFFILIATE_TAG", "cfg-21")

    link = build_amazon_search_link("samsung s24")
    assert link == "https://example.com/s?k=samsung+s24&tag=cfg-21"
