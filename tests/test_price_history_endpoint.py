"""
GET /products/{product_key}/price-history tests.

The endpoint serves ONLY persisted real PriceSnapshot rows from the catalog
(app/storage/store.py): real snapshots, chronological order, per-offer
identity never mixed across stores/variants, and a clean empty response when
history is unavailable or the catalog is disabled.  It must never scrape a
marketplace, spawn Playwright, or trigger the connectors.
"""

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app
from app.storage.store import get_store, reset_store

client = TestClient(app)


class _DisabledSettings:
    catalog_enabled = False
    rate_limit_enabled = False   # requested by the rate-limit middleware
    metrics_enabled = False      # requested by the metrics middleware


def _amazon(title="Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
            price=62999.0, product_key="samsung-galaxy-s24-onyx-black-128gb",
            asin="B0BLAHBLAH", **extra):
    return {
        "title": title,
        "product_key": product_key,
        "platform": "Amazon",
        "price_value": price,
        "price_display": "\u20b962,999",
        "url": f"https://www.amazon.in/dp/{asin}",
        "image": "https://example.com/s24.jpg",
        **extra,
    }


def _flipkart(title="Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
              price=64999.0, product_key="samsung-galaxy-s24-onyx-black-128gb",
              pid="MOBH7GF3KQFTCEG5", **extra):
    return {
        "title": title,
        "product_key": product_key,
        "platform": "Flipkart",
        "price_value": price,
        "price_display": "\u20b964,999",
        "url": f"https://www.flipkart.com/galaxy-s24/p/itm{pid}?pid={pid}",
        "image": "",
        **extra,
    }


def _use_store(tmp_path, monkeypatch):
    """Point the process store at a fresh tmp dir and reset the singleton."""
    monkeypatch.setenv("DEALCOMPARE_DATA_DIR", str(tmp_path))
    reset_store()
    return get_store()


def test_returns_real_snapshots_chronologically(tmp_path, monkeypatch):
    store = _use_store(tmp_path, monkeypatch)
    try:
        # Upserting adds the first-seen observation, then one per price change.
        store.upsert_search_results("galaxy s24", "galaxy s24",
                                    [_amazon(price=62999.0)])
        store.upsert_search_results("galaxy s24", "galaxy s24",
                                    [_amazon(price=61999.0)])
        store.upsert_search_results("galaxy s24", "galaxy s24",
                                    [_amazon(price=59999.0)])

        res = client.get(
            "/products/samsung-galaxy-s24-onyx-black-128gb/price-history"
        )

        assert res.status_code == 200
        data = res.json()
        assert data["product_key"] == "samsung-galaxy-s24-onyx-black-128gb"
        assert data["catalog_enabled"] is True
        assert len(data["offers"]) == 1
        offer = data["offers"][0]
        assert offer["platform"] == "Amazon"
        assert offer["current_price"] == 59999.0
        # Only the real observed prices, oldest first.
        assert [p["price_value"] for p in offer["observations"]] == [
            62999.0, 61999.0, 59999.0,
        ]
        stamps = [p["observed_at"] for p in offer["observations"]]
        assert stamps == sorted(stamps)
        assert offer["url"].startswith("https://www.amazon.in/")
    finally:
        reset_store()


def test_marketplaces_stay_separate_series(tmp_path, monkeypatch):
    store = _use_store(tmp_path, monkeypatch)
    try:
        store.upsert_search_results("galaxy s24", "galaxy s24", [
            _amazon(price=62999.0),
            _flipkart(price=64999.0),
        ])
        store.upsert_search_results("galaxy s24", "galaxy s24", [
            _amazon(price=59999.0),
        ])

        res = client.get(
            "/products/samsung-galaxy-s24-onyx-black-128gb/price-history"
        )

        assert res.status_code == 200
        offers = {o["platform"]: o for o in res.json()["offers"]}
        assert set(offers) == {"Amazon", "Flipkart"}
        # Each series carries ONLY its own marketplace's real observations.
        assert [p["price_value"] for p in offers["Amazon"]["observations"]] == [
            62999.0, 59999.0,
        ]
        assert [p["price_value"] for p in offers["Flipkart"]["observations"]] == [
            64999.0,
        ]
    finally:
        reset_store()


def test_identity_isolated_across_variants(tmp_path, monkeypatch):
    store = _use_store(tmp_path, monkeypatch)
    try:
        # Two genuinely different SKUs on the same marketplace.
        store.upsert_search_results("macbook", "macbook", [
            _amazon(title="Apple MacBook Pro (16 GB RAM, 512 GB SSD)",
                    product_key="apple-macbook-pro-16gb", asin="B0SIXTEEN"),
            _amazon(title="Apple MacBook Pro (8 GB RAM, 512 GB SSD)",
                    product_key="apple-macbook-pro-8gb", asin="B0EIGHTE"),
        ])
        store.upsert_search_results("macbook", "macbook", [
            _amazon(title="Apple MacBook Pro (16 GB RAM, 512 GB SSD)",
                    price=184999.0, product_key="apple-macbook-pro-16gb",
                    asin="B0SIXTEEN"),
        ])

        res = client.get("/products/apple-macbook-pro-16gb/price-history")

        assert res.status_code == 200
        offers = res.json()["offers"]
        # Only the 16 GB listing is returned; the 8 GB history never leaks in.
        assert len(offers) == 1
        assert offers[0]["product_key"] == "apple-macbook-pro-16gb"
        assert [p["price_value"] for p in offers[0]["observations"]] == [
            _amazon()["price_value"], 184999.0,
        ]
    finally:
        reset_store()


def test_unseen_product_key_returns_honest_empty(tmp_path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    try:
        res = client.get("/products/never-seen-key/price-history")

        assert res.status_code == 200
        assert res.json() == {
            "product_key": "never-seen-key",
            "catalog_enabled": True,
            "offers": [],
        }
    finally:
        reset_store()


def test_catalog_disabled_returns_clean_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "get_settings", lambda: _DisabledSettings())
    _use_store(tmp_path, monkeypatch)
    try:
        store = get_store()
        store.upsert_search_results("galaxy s24", "galaxy s24",
                                    [_amazon(price=62999.0)])

        res = client.get(
            "/products/samsung-galaxy-s24-onyx-black-128gb/price-history"
        )

        # Clean honest empty response — never an error or fabricated points.
        assert res.status_code == 200
        assert res.json() == {
            "product_key": "samsung-galaxy-s24-onyx-black-128gb",
            "catalog_enabled": False,
            "offers": [],
        }
    finally:
        reset_store()


def test_history_endpoint_never_touches_connectors(tmp_path, monkeypatch):
    """The endpoint reads the catalog and nothing else (no scraping)."""
    _use_store(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(main_module, "search_with_marketplaces",
                            lambda *a: pytest.fail("must not scrape"))
        res = client.get("/products/anything/price-history")
        assert res.status_code == 200
    finally:
        reset_store()


def test_chronological_order_enforced_even_for_out_of_order_file(
        tmp_path, monkeypatch):
    """The endpoint sorts observations by observed_at, not file order."""
    store = _use_store(tmp_path, monkeypatch)
    try:
        store.upsert_search_results("galaxy s24", "galaxy s24",
                                    [_amazon(price=62999.0)])
        # Simulate a persisted file whose snapshot rows happen to be stored
        # out of chronological order — the store/endpoint must re-sort.
        store._doc["snapshots"]["amazon:asin/B0BLAHBLAH"] = [
            {"price_value": 61999.0, "observed_at": 200.0},
            {"price_value": 62999.0, "observed_at": 100.0},
            {"price_value": 59999.0, "observed_at": 300.0},
        ]
        store._flush()

        res = client.get(
            "/products/samsung-galaxy-s24-onyx-black-128gb/price-history"
        )

        assert res.status_code == 200
        obs = res.json()["offers"][0]["observations"]
        assert [p["price_value"] for p in obs] == [62999.0, 61999.0, 59999.0]
        assert [p["observed_at"] for p in obs] == [100.0, 200.0, 300.0]
    finally:
        reset_store()