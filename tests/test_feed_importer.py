"""
Feed importer tests (app/feed/importer.py).

Covers end-to-end ingestion: accepted/rejected honesty, source kind "feed",
feed provenance, SKU-anchored strong identity, idempotent re-ingestion, price
snapshots, merging into an existing Amazon ASIN product while keeping separate
MarketplaceOffers, no search_index without an explicit query_key, and backward
compatibility with pre-feed catalog files.
"""

import json

from app.feed.importer import ingest_feed
from app.feed.parser import rows_from_json
from app.storage.store import JsonCatalogStore

S24_TITLE = "Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)"
S24_KEY = "samsung-galaxy-s24-128gb"


def _amazon(title=S24_TITLE, price=62999.0, asin="B0BLAHBLAH",
            product_key=S24_KEY, **extra):
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


def _feed_row(**overrides):
    row = {
        "title": S24_TITLE,
        "sku": "S24-BLACK-128",
        "price": "\u20b962,999",
        "actual_price": "\u20b970,999",
        "availability": "in stock",
        "url": "https://acme.example.com/s24",
        "image": "https://acme.example.com/s24.jpg",
        "store": "Acme Store",
        "brand": "Samsung",
    }
    row.update(overrides)
    return row


def test_ingests_valid_json_rows_and_marks_feed_source(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    rows = rows_from_json(json.dumps([
        _feed_row(),
        _feed_row(sku="S24-BLUE-128", price="61999", url="https://acme.example.com/s24-blue"),
    ]))

    result = ingest_feed("acme", rows, store=store)
    assert result.source == "acme"
    assert result.accepted == 2
    assert result.rejected == 0

    counts = store.counts()
    assert counts["products"] == 1   # same title/variant -> one canonical product
    assert counts["offers"] == 2     # two distinct listings (different URLs/SKUs)
    assert counts["searches"] == 0   # no query_key supplied

    sources = store.sources()
    assert sources["acme"]["kind"] == "feed"
    assert sources["acme"]["last_ok_at"] is not None


def test_offer_rows_carry_feed_provenance_and_extras(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    ingest_feed("acme", [_feed_row()], store=store)

    offers = list(store._doc["offers"].values())
    assert len(offers) == 1
    row = offers[0]
    assert row["feed_provenance"] == "acme"
    assert row["original_price"] == 70999.0
    assert row["availability"] == "in_stock"
    assert row["marketplace"] == "Acme Store"


def test_keyless_and_unpriced_rows_rejected(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    rows = [
        _feed_row(),                              # valid
        {**_feed_row(), "title": ""},             # no title -> no identity
        {**_feed_row(), "price": None},           # unpriced
        {**_feed_row(), "price": "free"},         # non-numeric price
        {**_feed_row(), "price": 0},              # zero price
        {**_feed_row(), "price": -5},             # negative price
        [1, 2, 3],                                # non-dict row
    ]
    result = ingest_feed("acme", rows, store=store)
    assert result.accepted == 1
    assert result.rejected == 6
    assert store.counts()["offers"] == 1


def test_all_invalid_batch_leaves_store_completely_untouched(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    ingest_feed("acme", [_feed_row()], store=store)
    before = store.counts()

    result = ingest_feed("acme", [{**_feed_row(), "price": None}], store=store)
    assert result.accepted == 0
    assert result.rejected == 1
    assert store.counts() == before          # no row, no source health, no file change
    assert len(store.sources()) == 1         # only the earlier successful source


def test_feed_sku_becomes_strong_identity_when_genuinely_supplied(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    row = {**_feed_row(), "url": None}        # SKU present, no product URL
    ingest_feed("acme", [row], store=store)

    oid = "acme store:feed/acme:S24-BLACK-128"
    assert store._doc["offers"][oid]["listing_id"] == "feed/acme:S24-BLACK-128"
    # snapshot row exists for the SKU-anchored offer id
    assert store.price_history(oid)[0]["price_value"] == 62999.0


def test_reingest_same_sku_price_is_idempotent(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    row = {**_feed_row(), "url": None}
    ingest_feed("acme", [row], store=store)
    ingest_feed("acme", [row], store=store)

    assert store.counts()["offers"] == 1
    assert store.counts()["snapshots"] == 1   # no new snapshot when price unchanged


def test_price_change_appends_snapshot(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    row = {**_feed_row(), "url": None}
    ingest_feed("acme", [row], store=store)
    ingest_feed("acme", [{**row, "price": "61999"}], store=store)

    assert store.counts()["offers"] == 1
    oid = "acme store:feed/acme:S24-BLACK-128"
    history = store.price_history(oid)
    assert [r["price_value"] for r in history] == [62999.0, 61999.0]


def test_feed_offer_merges_into_existing_amazon_product(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    store.upsert_search_results(
        "samsung phone", "samsung phone", [_amazon()],
        source_updates=[{"key": "amazon", "display_name": "Amazon", "kind": "api", "ok": True}],
    )
    # A feed row for the identical variant, from a different store, with no
    # URL and no SKU: identity relies on the attribute SKU -> merges.
    rows = [{**_feed_row(), "sku": None, "url": None, "price": "61999"}]
    ingest_feed("acme", rows, store=store)

    counts = store.counts()
    assert counts["products"] == 1           # same canonical product, not a new one
    assert counts["offers"] == 2             # Amazon + Acme offers stay separate

    products = list(store._doc["products"].values())
    assert len(products) == 1
    assert sorted(products[0]["query_keys"]) == ["samsung phone"]


def test_feed_offers_from_different_stores_stay_separate_offers(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    ingest_feed("acme", [_feed_row(store="Acme Store")], store=store)
    ingest_feed("beta", [{**_feed_row(store="Beta Shop"), "sku": "BETA-1", "url": None}], store=store)

    assert store.counts()["products"] == 1   # same variant still one product
    assert store.counts()["offers"] == 2     # but two distinct MarketplaceOffers


def test_no_search_index_without_query_key(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    result = ingest_feed("acme", [_feed_row()], store=store, query_key=None)
    assert result.accepted == 1
    assert store.search_offers(S24_TITLE) is None
    assert store.counts()["searches"] == 0


def test_search_index_written_when_query_key_given(tmp_path):
    store = JsonCatalogStore(str(tmp_path))
    result = ingest_feed("acme", [_feed_row()], store=store, query_key="samsung s24")
    assert result.accepted == 1

    stored = store.search_offers("samsung s24")
    assert stored is not None and len(stored) == 1
    assert stored[0]["title"] == S24_TITLE
    assert stored[0]["marketplace"] == "Acme Store"
    assert store.counts()["searches"] == 1


def test_backward_compatible_catalog_load(tmp_path):
    old_doc = {
        "version": 1,
        "sources": {},
        "products": {
            "P1": {
                "id": "P1",
                "title": "Old Product",
                "category": None,
                "sku": [["key", "old-product"]],
                "strong": None,
                "eans": [],
                "query_keys": ["q"],
                "first_seen_at": 1.0,
                "updated_at": 1.0,
            }
        },
        "offers": {
            "old:store/old-product": {
                "id": "old:store/old-product",
                "product_id": "P1",
                "marketplace": "Old Store",
                "listing_id": None,
                "url": "",
                "title": "Old Product",
                "product_key": "old-product",
                "price_value": 100.0,
                "price_display": "\u20b9100",
                "image": "",
                "strong": None,
                "sku": [["key", "old-product"]],
                "data": {"title": "Old Product", "product_key": "old-product", "platform": "Old Store", "price_value": 100.0},
                "first_seen_at": 1.0,
                "updated_at": 1.0,
            }
        },
        "snapshots": {"old:store/old-product": [{"price_value": 100.0, "observed_at": 1.0}]},
        "search_index": {"q": {"updated_at": 1.0, "product_ids": ["P1"], "offer_ids": ["old:store/old-product"]}},
    }
    (tmp_path / "catalog.json").write_text(json.dumps(old_doc), encoding="utf-8")

    store = JsonCatalogStore(str(tmp_path))
    assert store.counts()["products"] == 1
    assert store.counts()["offers"] == 1
    # the pre-feed offer is still served verbatim from the old-format file
    assert store.search_offers("q") == [old_doc["offers"]["old:store/old-product"]["data"]]

    # feed ingestion still works alongside the old-format rows
    result = ingest_feed("acme", [_feed_row()], store=store)
    assert result.accepted == 1
    assert store.counts()["products"] == 2
    assert store.counts()["offers"] == 2


def test_cli_ingests_file(monkeypatch, tmp_path):
    from app.feed.__main__ import main
    from app.storage.store import reset_store

    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps([_feed_row()]), encoding="utf-8")
    monkeypatch.setenv("DEALCOMPARE_DATA_DIR", str(tmp_path / "data"))
    reset_store()
    try:
        rc = main(["--source", "acme", "--file", str(feed)])
        assert rc == 0
    finally:
        reset_store()

    stored = json.loads((tmp_path / "data" / "catalog.json").read_text(encoding="utf-8"))
    assert stored["sources"]["acme"]["kind"] == "feed"
    assert len(stored["offers"]) == 1