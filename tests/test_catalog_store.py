"""
JsonCatalogStore tests (Buyhatke-style catalog foundation).

Covers: verbatim round-trip of scraper-shaped offers, same-listing upsert
(dedupe) across re-scrapes, price-history snapshots + cap, cross-store product
matching, variant splitting, query freshness windows, empty/corrupt fail-open,
and persistence across store re-instantiation (restart survival).
"""

import json
import time

import pytest

from app.storage.store import JsonCatalogStore, get_store, reset_store


def _amazon(title="Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
            price=62999.0, asin="B0BLAHBLAH", product_key="samsung-galaxy-s24-5g-onyx-black-128gb",
            **extra):
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
              price=64999.0, pid="MOBH7GF3KQFTCEG5",
              product_key="samsung-galaxy-s24-5g-onyx-black-128gb", **extra):
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


def test_upsert_persists_verbatim_offers_and_search_entry(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    offer = _amazon()

    store.upsert_search_results(
        "iphone 15", "iphone 15", [offer],
        source_updates=[
            {"key": "amazon", "display_name": "Amazon", "kind": "scrape", "ok": True}
        ],
    )

    counts = store.counts()
    assert counts["products"] == 1
    assert counts["offers"] == 1
    assert counts["searches"] == 1

    stored = store.search_offers("iphone 15")
    assert stored == [offer]  # verbatim round-trip, field-for-field
    assert stored[0] is not offer  # deep copy, not aliasing

    sources = store.sources()
    assert sources["amazon"]["display_name"] == "Amazon"
    assert sources["amazon"]["kind"] == "scrape"
    assert sources["amazon"]["last_ok_at"] is not None
    assert sources["amazon"]["error"] is None


def test_same_listing_reupsert_updates_not_duplicates(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results("q", "q", [_amazon(price=62999.0)])
    store.upsert_search_results("q", "q", [_amazon(price=61999.0)])
    store.upsert_search_results("q", "q", [_amazon(price=61999.0)])

    counts = store.counts()
    assert counts["products"] == 1
    assert counts["offers"] == 1  # same ASIN -> same offer row, never duplicated


def test_price_change_appends_price_history(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results("q", "q", [_amazon(price=62999.0)])
    store.upsert_search_results("q", "q", [_amazon(price=61999.0)])
    store.upsert_search_results("q", "q", [_amazon(price=59999.0)])

    history = store.price_history("amazon:asin/B0BLAHBLAH")
    assert [row["price_value"] for row in history] == [62999.0, 61999.0, 59999.0]
    # first_seen price is the first observation; latest price is current.
    assert history[-1]["observed_at"] >= history[0]["observed_at"]


def test_price_history_capped_by_limit(tmp_path, monkeypatch):
    from app.storage import store as store_module
    monkeypatch.setattr(
        store_module, "get_settings",
        lambda: type("_Cap", (), {"price_history_limit": 2})(),
    )
    store = JsonCatalogStore(str(tmp_path))
    for price in (100.0, 90.0, 80.0):
        store.upsert_search_results("q", "q", [_amazon(price=price)])

    history = store.price_history("amazon:asin/B0BLAHBLAH")
    assert [row["price_value"] for row in history] == [90.0, 80.0]


def test_same_sku_across_stores_merges_into_one_product(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results(
        "samsung phone", "samsung phone",
        [_amazon(), _flipkart()],
    )

    counts = store.counts()
    assert counts["products"] == 1  # Amazon + Flipkart share one canonical product
    assert counts["offers"] == 2

    products = store._doc["products"]
    assert len(products) == 1
    first = next(iter(products.values()))
    assert sorted(first["query_keys"]) == ["samsung phone"]


def test_different_variant_creates_separate_products(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results(
        "macbook", "macbook",
        [
            _amazon(title="Apple MacBook Pro (16 GB RAM, 512 GB SSD)",
                    product_key="apple-macbook-pro-16gb"),
            _amazon(title="Apple MacBook Pro (8 GB RAM, 512 GB SSD)",
                    product_key="apple-macbook-pro-8gb", asin="B0OTHEROTH"),
        ],
    )

    assert store.counts()["products"] == 2  # genuinely different RAM -> separate SKUs


def test_search_offers_respects_freshness_window(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results("iphone 15", "iphone 15", [_amazon()])

    assert store.search_offers("iphone 15") == [_amazon()]
    # max_age_seconds=0: the entry is necessarily older than "now" -> not served.
    assert store.search_offers("iphone 15", max_age_seconds=0) is None
    assert store.search_offers("never-searched") is None


def test_empty_upsert_is_noop(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results("q", "q", [])
    assert store.counts() == {
        "sources": 0, "products": 0, "offers": 0, "snapshots": 0, "searches": 0,
    }


def test_invalid_offers_never_persisted(tmp_path):
    """
    Persistence mirrors the aggregator's validity rule: an offer without a
    usable product_key or without a price > 0 is not a comparable listing and
    must NEVER enter the catalog (no row, no snapshot, no search index entry).
    """
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results(
        "q", "q",
        [
            _amazon(),  # valid
            {**_amazon(), "product_key": ""},          # keyless
            {**_amazon(), "product_key": "   "},       # whitespace-only key
            {**_amazon(), "price_value": 0},           # zero price
            {**_amazon(), "price_value": None},        # unpriced placeholder
            {**_amazon(), "price_value": -5.0},        # negative price
        ],
        source_updates=[
            {"key": "amazon", "display_name": "Amazon", "kind": "scrape", "ok": True}
        ],
    )

    counts = store.counts()
    assert counts["products"] == 1   # only the valid offer persisted
    assert counts["offers"] == 1
    assert counts["snapshots"] == 1  # no None/0/-1 priced snapshot rows
    assert store.search_offers("q") == [_amazon()]

    history = store.price_history("amazon:asin/B0BLAHBLAH")
    assert [row["price_value"] for row in history] == [62999.0]


def test_all_invalid_batch_touches_nothing(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results("q", "q", [_amazon()])  # a clean baseline
    before = store.counts()

    store.upsert_search_results(
        "q", "q",
        [{**_amazon(), "price_value": None}, {**_amazon(), "product_key": ""}],
        source_updates=[
            {"key": "amazon", "display_name": "Amazon", "kind": "scrape", "ok": True}
        ],
    )

    assert store.counts() == before       # invalid batch: nothing written at all
    assert store.search_offers("q") == [_amazon()]


def test_corrupt_file_fails_open(tmp_path):
    (tmp_path / "catalog.json").write_text("{not valid json", encoding="utf-8")
    store = JsonCatalogStore(str(tmp_path))
    assert store.counts()["products"] == 0  # starts empty instead of raising
    store.upsert_search_results("q", "q", [_amazon()])  # and recovers on write
    assert store.counts()["products"] == 1


def test_persistence_survives_reinstantiation(tmp_path):
    first = JsonCatalogStore(str(tmp_path))
    first.upsert_search_results("iphone 15", "iphone 15", [_amazon(price=62999.0)])

    second = JsonCatalogStore(str(tmp_path))  # "process restart" -> reloads file
    assert second.counts()["offers"] == 1
    assert second.search_offers("iphone 15") == [_amazon(price=62999.0)]
    assert second.price_history("amazon:asin/B0BLAHBLAH")[0]["price_value"] == 62999.0


def test_get_store_reads_env_and_survives_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("DEALCOMPARE_DATA_DIR", str(tmp_path))
    reset_store()
    try:
        store = get_store()
        assert store.path == str(tmp_path / "catalog.json")

        store.upsert_search_results("q", "q", [_amazon()])
        reset_store()

        reloaded = get_store()  # singleton re-created -> re-reads the file
        assert reloaded is not store
        assert reloaded.counts()["offers"] == 1
        assert reloaded.path == str(tmp_path / "catalog.json")
    finally:
        reset_store()