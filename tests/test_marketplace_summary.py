"""
Marketplace-summary tests for the additive /search `marketplaces` field.

The summary is derived ONLY from actual connector execution: each active
source that ran is reported with its REAL offer count and ok status; a
marketplace that did not return offers is never marked ok, and a disabled
marketplace (Ajio by default) never appears at all.  Nothing here may
manufacture availability.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import search_service
from app.services.search_service import search_with_marketplaces

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Env-var tests mutate settings; never leak the cache across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _offer(platform, price=1000.0):
    return {
        "title": "Apple iPhone 15 (128 GB) - Black",
        "product_key": "apple-iphone-15-128gb",
        "platform": platform,
        "price_value": price,
        "price_display": f"\u20b9{int(price):,}",
        "url": f"https://example.com/{platform.lower()}/{int(price)}",
        "image": "https://example.com/img.jpg",
    }


def _stub(monkeypatch, by_platform):
    def source(key):
        def _search(q):
            return by_platform.get(key, [])

        return _search

    monkeypatch.setattr(
        search_service, "search_amazon", source("Amazon")
    )
    monkeypatch.setattr(
        search_service, "search_flipkart", source("Flipkart")
    )
    monkeypatch.setattr(
        search_service, "search_myntra", source("Myntra")
    )
    monkeypatch.setattr(
        search_service, "search_ajio", source("Ajio")
    )


def _summary_map(outcome):
    return {m["key"]: m for m in outcome["marketplaces"]}


# A. one marketplace ---------------------------------------------------------

def test_summary_one_marketplace_returns_only_what_ran(monkeypatch):
    _stub(monkeypatch, {"Amazon": [_offer("Amazon")]})

    outcome = asyncio.run(search_with_marketplaces("iphone 15"))

    assert len(outcome["products"]) == 1
    by_key = _summary_map(outcome)
    # Defaults: amazon api, flipkart api, myntra http; ajio disabled (absent).
    assert set(by_key) == {"amazon", "flipkart", "myntra"}
    assert by_key["amazon"]["offer_count"] == 1 and by_key["amazon"]["ok"] is True
    assert by_key["amazon"]["kind"] == "api"
    assert by_key["amazon"]["display_name"] == "Amazon"
    assert by_key["flipkart"]["offer_count"] == 0 and by_key["flipkart"]["ok"] is False
    assert by_key["myntra"]["offer_count"] == 0 and by_key["myntra"]["ok"] is False
    assert "ajio" not in by_key


# B. two marketplaces --------------------------------------------------------

def test_summary_two_marketplaces_endpoint(monkeypatch):
    _stub(monkeypatch, {
        "Flipkart": [_offer("Flipkart", 9000.0)],
        "Amazon": [_offer("Amazon", 9500.0)],
    })

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    assert "marketplaces" in data
    by_key = {m["key"]: m for m in data["marketplaces"]}
    assert set(by_key) == {"amazon", "flipkart", "myntra"}
    assert by_key["amazon"]["ok"] is True and by_key["amazon"]["offer_count"] == 1
    assert by_key["flipkart"]["ok"] is True and by_key["flipkart"]["offer_count"] == 1
    assert by_key["myntra"]["ok"] is False and by_key["myntra"]["offer_count"] == 0


# C. three marketplaces ------------------------------------------------------

def test_summary_three_marketplaces_and_cross_store_group(monkeypatch):
    # Same SKU on all three active stores -> ONE product card, three offers.
    _stub(monkeypatch, {
        "Amazon": [_offer("Amazon", 9500.0)],
        "Flipkart": [_offer("Flipkart", 9000.0)],
        "Myntra": [_offer("Myntra", 9100.0)],
    })

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 1
    assert {o["platform"] for o in data["results"][0]["offers"]} == {
        "Amazon", "Flipkart", "Myntra",
    }
    by_key = {m["key"]: m for m in data["marketplaces"]}
    assert set(by_key) == {"amazon", "flipkart", "myntra"}
    assert all(by_key[k]["ok"] is True for k in ("amazon", "flipkart", "myntra"))
    assert all(by_key[k]["offer_count"] == 1 for k in ("amazon", "flipkart", "myntra"))


# D. all marketplaces empty --------------------------------------------------

def test_summary_all_empty_is_honest_and_reported(monkeypatch):
    _stub(monkeypatch, {})

    res = client.get("/search", params={"query": "unobtainium xyz"})

    assert res.status_code == 200
    data = res.json()
    assert data["results"] == []
    by_key = {m["key"]: m for m in data["marketplaces"]}
    assert set(by_key) == {"amazon", "flipkart", "myntra"}
    for m in data["marketplaces"]:
        assert m["offer_count"] == 0 and m["ok"] is False


# E. one connector failure does not sink the search ---------------------------

def test_summary_connector_failure_isolated_from_success(monkeypatch):
    def boom(q):
        raise RuntimeError("flipkart down")

    def amazon(q):
        return [_offer("Amazon")]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    monkeypatch.setattr(search_service, "search_flipkart", boom)
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 1  # Amazon's real offers still served
    by_key = {m["key"]: m for m in data["marketplaces"]}
    assert by_key["amazon"]["ok"] is True and by_key["amazon"]["offer_count"] == 1
    assert by_key["flipkart"]["ok"] is False and by_key["flipkart"]["offer_count"] == 0
    assert by_key["myntra"]["ok"] is False


def test_summary_every_source_raising_is_honest_empty_not_an_error(monkeypatch):
    """ALL sources crashing -> HTTP 200 + [] + per-source ok:false.

    The strongest form of the failure-isolation contract: failed sources are
    honest empty, never an HTTP error and never fabricated data.
    """
    def boom(q):
        raise RuntimeError("source down")

    monkeypatch.setattr(search_service, "search_amazon", boom)
    monkeypatch.setattr(search_service, "search_flipkart", boom)
    monkeypatch.setattr(search_service, "search_myntra", boom)
    monkeypatch.setattr(search_service, "search_ajio", boom)

    res = client.get("/search", params={"query": "iphone 15"})

    assert res.status_code == 200
    data = res.json()
    assert data["results"] == []
    by_key = {m["key"]: m for m in data["marketplaces"]}
    assert set(by_key) == {"amazon", "flipkart", "myntra"}
    for m in data["marketplaces"]:
        assert m["offer_count"] == 0 and m["ok"] is False


# F/G. missing Amazon + Flipkart credentials ---------------------------------

def test_summary_missing_creds_are_honest_empty_per_source(monkeypatch):
    # Defaults are "api" but the credentials are UNset, so the real Amazon /
    # Flipkart adapters must short-circuit to [] WITHOUT any network attempt.
    # Myntra (HTTP) would hit the network, so it is stubbed.
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    calls = []

    def fake_post(*a, **k):  # pragma: no cover - must never be reached
        calls.append(1)
        raise AssertionError("no network call may happen without credentials")

    import app.scrapers.amazon_creators as creators
    monkeypatch.setattr(creators.requests, "post", fake_post)

    outcome = asyncio.run(search_with_marketplaces("iphone 15"))

    assert outcome["products"] == []
    by_key = _summary_map(outcome)
    assert by_key["amazon"]["ok"] is False and by_key["amazon"]["offer_count"] == 0
    assert by_key["flipkart"]["ok"] is False and by_key["flipkart"]["offer_count"] == 0
    assert by_key["myntra"]["ok"] is False
    assert calls == []


# H. no fabricated offers in the summary --------------------------------------

def test_summary_counts_never_exceed_real_offers(monkeypatch):
    amazon_offers = [_offer("Amazon", 9000.0), _offer("Amazon", 9100.0)]
    _stub(monkeypatch, {"Amazon": amazon_offers})

    outcome = asyncio.run(search_with_marketplaces("iphone 15"))

    amazon_summary = _summary_map(outcome)["amazon"]
    assert amazon_summary["offer_count"] == len(amazon_offers)
    assert len([p for p in outcome["products"] if p["platform"] == "Amazon"]) == (
        amazon_summary["offer_count"]
    )


# Summary survives the TTL cache without a second run -------------------------

def test_summary_reused_from_cache(monkeypatch):
    calls = {"n": 0}

    def amazon(q):
        calls["n"] += 1
        return [_offer("Amazon")]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])

    first = asyncio.run(search_with_marketplaces("iphone 15"))
    second = asyncio.run(search_with_marketplaces("iphone 15"))

    assert len(first["products"]) == 1
    assert second["products"] == first["products"]
    assert second["marketplaces"] == first["marketplaces"]
    assert calls["n"] == 1  # identical query served from cache