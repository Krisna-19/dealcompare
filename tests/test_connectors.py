"""
Marketplace connector tests (app/connectors/*).

The connector list is the declarative source registry; each connector resolves
its retrieval callable dynamically from search_service so the long-standing
test pattern of monkeypatching `search_service.search_<platform>` keeps working.
"""

from app.connectors.base import MarketplaceConnector, iter_default_connectors
from app.connectors.registry import DEFAULT_CONNECTORS
from app.services import search_service


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