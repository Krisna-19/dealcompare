"""
Marketplace connector tests (app/connectors/*).

The connector list is the declarative source registry; each connector resolves
its retrieval callable dynamically from search_service so the long-standing
test pattern of monkeypatching `search_service.search_<platform>` keeps working.

Phase F: the connector's *runtime* behaviour is data-source driven.  The live
`<key>_data_source` setting decides `.data_source`, `.active_kind`
("api"/"http"/"scrape"/"deferred") and `.enabled`; a marketplace configured as
"disabled" drops out of get_active_connectors() entirely.
"""

import pytest

from app.connectors.base import MarketplaceConnector, iter_default_connectors
from app.connectors.registry import DEFAULT_CONNECTORS, get_active_connectors
from app.core.config import get_settings
from app.services import search_service


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Env-var tests mutate settings; never leak the cache across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_connectors_declared():
    keys = [c.key for c in DEFAULT_CONNECTORS]
    assert keys == ["amazon", "flipkart", "myntra", "ajio"]
    assert {c.attr for c in DEFAULT_CONNECTORS} == {
        "search_amazon", "search_flipkart", "search_myntra", "search_ajio",
    }


def test_connector_kinds_and_display_names():
    by_key = {c.key: c for c in DEFAULT_CONNECTORS}
    assert by_key["amazon"].display_name == "Amazon"
    assert by_key["flipkart"].display_name == "Flipkart"
    assert by_key["amazon"].kind == "scrape"
    assert by_key["myntra"].kind == "http"
    assert by_key["ajio"].kind == "scrape"
    assert by_key["flipkart"].kind in {"scrape", "api"}


def test_resolve_returns_the_live_search_function():
    connector = MarketplaceConnector("amazon", "Amazon", "scrape", "search_amazon")
    assert connector.resolve() is search_service.search_amazon


def test_resolve_follows_test_monkeypatching(monkeypatch):
    connector = MarketplaceConnector("amazon", "Amazon", "scrape", "search_amazon")
    fake = lambda q: ["fake"]  # noqa: E731
    monkeypatch.setattr(search_service, "search_amazon", fake)

    assert connector.resolve() is fake
    assert connector.run("iphone 15") == ["fake"]


def test_missing_attr_resolves_to_none_not_raise():
    connector = MarketplaceConnector("ghost", "Ghost", "scrape", "search_ghost")
    assert connector.resolve() is None
    assert connector.run("q") == []  # honest empty, never a crash


def test_iter_default_connectors_matches_registry():
    assert list(iter_default_connectors()) == list(DEFAULT_CONNECTORS)


# --- Phase F: data-source driven routing ------------------------------------

def test_active_kind_maps_to_data_source(monkeypatch):
    monkeypatch.setenv("AMAZON_DATA_SOURCE", "api")
    get_settings.cache_clear()
    assert MarketplaceConnector("amazon", "Amazon", "scrape", "search_amazon").active_kind == "api"

    monkeypatch.setenv("AMAZON_DATA_SOURCE", "scraper")
    get_settings.cache_clear()
    assert MarketplaceConnector("amazon", "Amazon", "scrape", "search_amazon").active_kind == "scrape"

    monkeypatch.setenv("MYNTRA_DATA_SOURCE", "http")
    get_settings.cache_clear()
    assert MarketplaceConnector("myntra", "Myntra", "http", "search_myntra").active_kind == "http"

    monkeypatch.setenv("MYNTRA_DATA_SOURCE", "scraper")
    get_settings.cache_clear()
    assert MarketplaceConnector("myntra", "Myntra", "http", "search_myntra").active_kind == "scrape"


def test_disabled_source_is_deferred(monkeypatch):
    monkeypatch.setenv("AJIO_DATA_SOURCE", "disabled")
    get_settings.cache_clear()
    connector = next(c for c in DEFAULT_CONNECTORS if c.key == "ajio")
    assert connector.data_source == "disabled"
    assert connector.active_kind == "deferred"
    assert connector.enabled is False


def test_unknown_marketplace_defaults_to_scraper_and_enabled():
    connector = MarketplaceConnector("ghost", "Ghost", "scrape", "search_ghost")
    assert connector.data_source == "scraper"
    assert connector.active_kind == "scrape"
    assert connector.enabled is True


def test_get_active_connectors_drops_disabled_marketplaces(monkeypatch):
    monkeypatch.setenv("AJIO_DATA_SOURCE", "disabled")
    get_settings.cache_clear()
    keys = [c.key for c in get_active_connectors()]
    assert keys == ["amazon", "flipkart", "myntra"]

    monkeypatch.setenv("AJIO_DATA_SOURCE", "scraper")
    get_settings.cache_clear()
    assert [c.key for c in get_active_connectors()] == [
        "amazon", "flipkart", "myntra", "ajio",
    ]


def test_all_sources_active_by_default():
    assert [c.key for c in get_active_connectors()] == [
        "amazon", "flipkart", "myntra", "ajio",
    ]