"""
Feed ingestion entry point (Phase 9).

ingest_feed() normalizes every row of a merchant feed onto the DealCompare
offer contract (app/feed/normalizer.py), then persists the valid offers through
the existing catalog store (app/storage/store.py::ingest_feed), which applies
the SAME validity / matching / offer-row / price-snapshot rules as the search
pipeline -- so a feed offer is just another MarketplaceOffer in the catalog.

Honesty rules:
  - Rows that cannot form a valid comparable offer (no title/product_key, no
    positive price) are rejected and counted; they are NEVER partially written.
  - The catalog, source health and file stay completely untouched when nothing
    valid survives a batch.
  - Re-ingesting the same SKU + price is idempotent (the existing offer row is
    updated); a price change appends a PriceSnapshot.
  - No search_index entry is created unless a query_key is explicitly passed.
  - Source health is recorded under the feed source with kind "feed".

This module is CLI-only (see app/feed/__main__.py); it is deliberately NOT
exposed as a public HTTP endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.feed.normalizer import normalize_record
from app.services.matching import compute_sku, compute_strong
from app.storage.store import get_store

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Honest summary of one feed ingestion."""

    source: str
    rows: int = 0
    accepted: int = 0
    rejected: int = 0


def _is_valid_offer(offer: Any) -> bool:
    """Mirror of aggregate_products()' validity rule (see store._ingest_offers_locked)."""
    if not isinstance(offer, dict):
        return False
    key = (offer.get("product_key") or "").strip()
    price = offer.get("price_value")
    title = offer.get("title") or ""
    return bool(key) and isinstance(price, (int, float)) and price > 0 and bool(title)


def _feed_identity(source: str):
    """Aggregator-aligned (sku, strong) for one feed offer.

    compute_strong() only assigns a strong listing id from a URL (or a
    Flipkart productId).  A feed that genuinely supplies a SKU but no product
    URL would otherwise have no durable identity, so re-ingesting the same
    feed row would duplicate it.  Only when a feed SKU is genuinely present
    AND no URL-derived strong id exists do we anchor identity on that merchant
    SKU.  Marketplace behaviour is untouched -- this callable is used solely
    during feed ingestion, never in the search/marketplace path.
    """

    def identity(offer: dict):
        sku = compute_sku(offer)
        strong = compute_strong(offer)
        feed_sku = (offer.get("product_id") or "").strip()
        if strong is None and feed_sku:
            strong = ("feed", f"{source}:{feed_sku}")
        return sku, strong

    return identity


def ingest_feed(source: str, records: list, query_key: Optional[str] = None,
                store=None) -> IngestResult:
    """Normalize *records* from *source* and persist them via the catalog.

    Args:
        source: Merchant/feed identifier (also recorded as the offer's
            feed_provenance and the source-health key).
        records: Feed rows (plain dicts) as given by app.feed.parser.
        query_key: Optional normalized query key.  When supplied, accepted
            offers additionally create a search_index entry; otherwise the
            feed never surfaces through the stored search path.
        store: JsonCatalogStore instance (defaults to the process singleton).

    Returns:
        An IngestResult with honest accepted/rejected counts.
    """
    store = store or get_store()
    records = list(records or [])

    offers: list = []
    rejected = 0
    for row in records:
        try:
            offer = normalize_record(row, source)
        except Exception as exc:  # a malformed row must never kill the batch
            logger.warning("Skipping malformed feed row for %s: %s", source, exc)
            rejected += 1
            continue
        if offer is None or not _is_valid_offer(offer):
            rejected += 1
            continue
        offers.append(offer)

    accepted = 0
    if offers:
        accepted = store.ingest_feed(
            source,
            offers,
            query_key=query_key,
            display_name=source,
            identity=_feed_identity(source),
        )
        # Defensive: the store applies the same validity rule; a row the store
        # drops cannot claim to be accepted.
        rejected += len(offers) - accepted

    return IngestResult(source=source, rows=len(records),
                        accepted=accepted, rejected=rejected)