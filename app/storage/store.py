"""
Restart-safe JSON catalog store.

Persists the DealCompare catalog (products, offers, price history, source
health, per-query search index) to a single JSON file that is rewritten
atomically on every mutation (write tmp + os.replace), so a crash mid-write
can never corrupt the previous snapshot.  The data directory is configurable
via DEALCOMPARE_DATA_DIR (or CATALOG_DATA_DIR in settings): point it at a
persistent disk in production so the catalog — and the price history it feeds
— survives restarts and redeploys.

Consistency rules:
  - The store is a single writer guarded by a threading.Lock; reads also take
    the lock and return deep copies so callers can never mutate shared state.
  - An offer is keyed by its stable listing identity; re-scraping the same
    listing updates the row instead of duplicating it, and any price change
    appends a PriceSnapshot (capped at price_history_limit entries).
  - A product groups matching offers across stores/queries using the same
    matching rules as the /search aggregator (app/services/matching.py).
  - search_index maps a normalized query to the offers most recently observed
    for it + the timestamp they were persisted; search_offers() serves those
    only while younger than the configured freshness window.

Failure contract:
  - A missing/corrupt catalog file fails open (empty catalog) so a storage
    problem can never take down /search; every catalog call in the search
    pipeline is additionally wrapped so the API degrades to today's live-only
    behaviour.
  - The store itself never raises on bad file contents; writing failures DO
    surface so operators can see persistent-disk problems in logs.
"""

import copy
import json
import logging
import os
import threading
import time
from typing import Optional

from app.core.config import get_settings
from app.services.matching import (
    build_offer_id,
    compute_sku,
    compute_strong,
    deserialize_sku,
    deserialize_strong,
    match_offer_to_product,
    serialize_sku,
    serialize_strong,
)

logger = logging.getLogger(__name__)

_CATALOG_FILE = "catalog.json"
_TMP_FILE = ".catalog.json.tmp"


def _default_doc():
    return {
        "version": 1,
        "sources": {},
        "products": {},
        "offers": {},
        "snapshots": {},
        "search_index": {},
    }


class JsonCatalogStore:
    """File-backed DealCompare catalog with in-process thread safety."""

    def __init__(self, data_dir: str):
        self.data_dir = os.path.abspath(data_dir)
        self.path = os.path.join(self.data_dir, _CATALOG_FILE)
        self._lock = threading.Lock()
        self._doc = _default_doc()
        self._load()

    # -- load / flush -------------------------------------------------------

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            if isinstance(doc, dict):
                self._doc = {**_default_doc(), **doc}
            else:
                logger.warning("Catalog file is not an object; starting empty")
        except FileNotFoundError:
            pass  # first run: empty catalog
        except (ValueError, TypeError) as exc:
            logger.warning("Catalog file unreadable (%s); starting empty", exc)

    def _flush(self):
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = os.path.join(self.data_dir, _TMP_FILE)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._doc, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, self.path)

    # -- lifecycle ----------------------------------------------------------

    def clear(self):
        """Drop every record and reset the catalog file (used by tests)."""
        with self._lock:
            self._doc = _default_doc()
            try:
                os.remove(self.path)
            except FileNotFoundError:
                pass

    def counts(self) -> dict:
        with self._lock:
            return {
                "sources": len(self._doc["sources"]),
                "products": len(self._doc["products"]),
                "offers": len(self._doc["offers"]),
                "snapshots": len(self._doc["snapshots"]),
                "searches": len(self._doc["search_index"]),
            }

    # -- query -> offers -----------------------------------------------------

    def search_offers(self, query_key: str, max_age_seconds: Optional[float] = None):
        """Stored offer dicts (verbatim original shape) for a query, or None.

        Returns None when the query was never persisted or when its entry is
        older than *max_age_seconds* (the served-stored freshness window).
        """
        with self._lock:
            entry = self._doc["search_index"].get(query_key)
            if not entry:
                return None
            if max_age_seconds is not None:
                age = time.time() - entry.get("updated_at", 0)
                if age > max_age_seconds:
                    return None
            rows = []
            for oid in entry.get("offer_ids", []):
                offer = self._doc["offers"].get(oid)
                if offer and offer.get("data"):
                    rows.append(copy.deepcopy(offer["data"]))
            return rows or None

    # -- persisting new search results ----------------------------------------

    def upsert_search_results(self, query_key: str, query: str, offer_dicts: list,
                              source_updates: Optional[list] = None):
        """Match/upsert every VALID offer of a fresh search into the catalog.

        *query_key* is the normalized query; *offer_dicts* are the verbatim
        scraper/API offer dicts.  Applies the SAME validity rule as the
        /search aggregator (aggregate_products): an offer without a usable
        product_key or with a non-positive price is not a comparable listing
        and is NEVER persisted -- so unpriced/keyless rows and None price
        snapshots cannot pollute the catalog.  Records price snapshots on
        change, attaches offers to canonical products, refreshes the query's
        search index and updates marketplace health.  No-op when no valid
        offer survives (invalid offers also leave source health untouched).
        """
        if not offer_dicts:
            return

        now = time.time()
        with self._lock:
            doc = self._doc
            seen_products, seen_offers = [], []

            for offer in offer_dicts:
                if not isinstance(offer, dict):
                    continue
                # Mirrors aggregate_products(): keyless or unpriced listings
                # are not valid comparable offers.
                key = (offer.get("product_key") or "").strip()
                price = offer.get("price_value")
                if not key or not price or price <= 0:
                    continue
                title = offer.get("title") or ""
                if not title:
                    continue

                sku = compute_sku(offer)
                strong = compute_strong(offer)

                product_id = match_offer_to_product(sku, strong, doc["products"])
                if product_id is None:
                    product_id = self._new_product_id(doc)
                    doc["products"][product_id] = {
                        "id": product_id,
                        "title": title,
                        "category": None,
                        "sku": serialize_sku(sku),
                        "strong": serialize_strong(strong),
                        "eans": [],
                        "query_keys": [query_key],
                        "first_seen_at": now,
                        "updated_at": now,
                    }
                else:
                    product = doc["products"][product_id]
                    if query_key not in product["query_keys"]:
                        product["query_keys"].append(query_key)
                    product["updated_at"] = now

                oid = build_offer_id(offer, strong)
                existing = doc["offers"].get(oid)
                if existing is None:
                    doc["offers"][oid] = {
                        "id": oid,
                        "product_id": product_id,
                        "marketplace": offer.get("platform") or "",
                        "listing_id": _listing_id(strong),
                        "url": offer.get("url") or "",
                        "title": title,
                        "product_key": offer.get("product_key") or "",
                        "price_value": offer.get("price_value"),
                        "price_display": offer.get("price_display") or "",
                        "image": offer.get("image") or "",
                        "strong": serialize_strong(strong),
                        "sku": serialize_sku(sku),
                        "data": copy.deepcopy(offer),
                        "first_seen_at": now,
                        "updated_at": now,
                    }
                    self._record_snapshot(doc, oid, offer.get("price_value"), now)
                else:
                    self._maybe_snapshot_price(
                        doc, existing, offer.get("price_value"), now
                    )
                    existing.update(
                        product_id=product_id,
                        marketplace=offer.get("platform") or existing.get("marketplace"),
                        url=offer.get("url") or existing.get("url"),
                        title=title,
                        product_key=offer.get("product_key") or existing.get("product_key"),
                        price_value=offer.get("price_value"),
                        price_display=offer.get("price_display") or "",
                        image=offer.get("image") or "",
                        updated_at=now,
                    )
                    existing["data"] = copy.deepcopy(offer)

                seen_products.append(product_id)
                seen_offers.append(oid)

            # Nothing valid survived the aggregator validity filter: leave the
            # catalog (search index, source health, file) completely untouched.
            if not seen_offers:
                return

            doc["search_index"][query_key] = {
                "updated_at": now,
                "product_ids": seen_products,
                "offer_ids": seen_offers,
            }

            for update in source_updates or []:
                self._apply_source(doc, update, now)

            self._flush()

    # -- price history --------------------------------------------------------

    def price_history(self, offer_id: str):
        """Snapshot rows for one offer as [{price_value, observed_at}, ...]."""
        with self._lock:
            rows = self._doc["snapshots"].get(offer_id, [])
            return copy.deepcopy(rows)

    def price_history_for_product_key(self, product_key: str):
        """Real snapshot history for every stored offer row of *product_key*.

        Read-only and strictly identity-preserving: the *product_key* of a
        persisted MarketplaceOffer row is matched exactly, and every returned
        series belongs to exactly ONE offer row (one marketplace listing, one
        SKU/variant).  Series for different stores / models / variants are
        kept apart and the snapshots of different offers are NEVER merged.
        Observations are returned chronological (by observed_at).

        This never scrapes, never triggers connectors/Playwright and never
        fabricates a point: only the persisted PriceSnapshot rows are returned.
        """
        key = (product_key or "").strip()
        with self._lock:
            doc = self._doc
            series = []
            for oid, offer in doc["offers"].items():
                if (offer.get("product_key") or "").strip() != key:
                    continue
                observations = sorted(
                    copy.deepcopy(doc["snapshots"].get(oid, [])),
                    key=lambda row: row.get("observed_at") or 0,
                )
                series.append({
                    "offer_id": oid,
                    "product_key": key,
                    "platform": offer.get("marketplace") or "",
                    "title": offer.get("title") or "",
                    "url": offer.get("url") or "",
                    "image": offer.get("image") or "",
                    "current_price": offer.get("price_value"),
                    "observations": observations,
                })
            return series

    # -- marketplace health ---------------------------------------------------

    def sources(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._doc["sources"])

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _new_product_id(doc) -> str:
        base = len(doc["products"]) + 1
        pid = f"P{base}"
        while pid in doc["products"]:
            base += 1
            pid = f"P{base}"
        return pid

    @staticmethod
    def _record_snapshot(doc, oid, price, ts):
        doc["snapshots"][oid] = [{"price_value": price, "observed_at": ts}]

    def _maybe_snapshot_price(self, doc, existing, price, ts):
        if existing.get("price_value") == price:
            return
        limit = int(getattr(get_settings(), "price_history_limit", 50) or 50)
        bucket = doc["snapshots"].setdefault(existing["id"], [])
        bucket.append({"price_value": price, "observed_at": ts})
        if len(bucket) > limit:
            del bucket[: len(bucket) - limit]

    def _apply_source(self, doc, update, now):
        key = (update.get("key") or "").strip().lower()
        if not key:
            return
        row = doc["sources"].setdefault(
            key, {
                "key": key,
                "display_name": update.get("display_name") or key.title(),
                "kind": update.get("kind") or "scrape",
                "enabled": True,
                "last_seen_at": None,
                "last_ok_at": None,
                "error": None,
            }
        )
        if update.get("display_name"):
            row["display_name"] = update["display_name"]
        if update.get("kind"):
            row["kind"] = update["kind"]
        row["last_seen_at"] = now
        if update.get("ok"):
            row["last_ok_at"] = now
            row["error"] = None
        elif update.get("error") is not None:
            row["error"] = update["error"]


def _listing_id(strong) -> Optional[str]:
    """A stable marketplace listing reference for the stored offer row."""
    parts = tuple(str(p) for p in strong if p is not None) if strong else ()
    return "/".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Process-wide singleton resolving the data dir lazily from the environment
# (so tests can point it at a fresh tmp dir without the env-cached Settings).
# ---------------------------------------------------------------------------

_store_singleton = None
_store_lock = threading.Lock()


def get_store() -> JsonCatalogStore:
    """The process-wide JsonCatalogStore for the configured data directory."""
    global _store_singleton
    with _store_lock:
        if _store_singleton is None:
            data_dir = os.environ.get(
                "DEALCOMPARE_DATA_DIR"
            ) or getattr(get_settings(), "catalog_data_dir", "./data")
            _store_singleton = JsonCatalogStore(data_dir)
        return _store_singleton


def reset_store():
    """Drop the cached store instance (used by tests between cases)."""
    global _store_singleton
    with _store_lock:
        _store_singleton = None