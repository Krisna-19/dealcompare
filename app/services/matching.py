"""
Product matching for the persisted catalog.

A new offer arriving from a scraper/API must be matched to an existing
canonical Product (so the catalog groups across stores and across queries) or
create a new one.  Matching reuses the EXACT same primitives the aggregator
uses to build /search cards -- attribute-compatible SKU identity and the
durable "strong id" (Flipkart productId, Amazon ASIN, Flipkart pid+path,
host+path) -- so a product group in the store and a product card from
aggregate_products() can never disagree about what is the same item.

Identity priority:
    1. Stable marketplace ids (productId / ASIN / pid) -- strongest signal.
    2. Brand + model + variant attributes (RAM/storage/colour/...).
    3. GTIN/EAN -- not currently exposed by any source; reserved for future
       API/feed connectors.
    4. Fallback product_key when a title has no detectable structure.

Core rule (mirrors aggregator._same_sku): two offers are the same product
when every attribute BOTH ensure explicitly states agrees; an attribute one
side omits is "unknown" and never forces a split.  Two offers from the same
listing strong id merge even when colours differ; genuinely different SKUs
(e.g. different RAM/storage) stay separate.
"""

from typing import Optional

from app.utils.text_utils import extract_variant_attributes
from app.aggregator.aggregator import (
    _sku_key,
    _strong_id_for_product,
    _same_sku,
)


# ---------------------------------------------------------------------------
# SKU / strong-id (de)serialization  (JSON cannot hold tuples)
# ---------------------------------------------------------------------------

def compute_sku(offer) -> tuple:
    """Canonical SKU attribute tuple for an offer dict (aggregator-aligned)."""
    return _sku_key(extract_variant_attributes(offer.get("title") or ""), offer)


def compute_strong(offer) -> Optional[tuple]:
    """Strong listing identity tuple for an offer dict, or None.

    Delegates to the aggregator, which returns None when the offer carries no
    URL and no explicit platform product id.
    """
    return _strong_id_for_product(offer)


def serialize_sku(sku) -> list:
    """SKU tuple -> JSON-safe list of [label, value] pairs."""
    return [[label, value] for label, value in sku]


def deserialize_sku(rows) -> tuple:
    """JSON-safe [label, value] rows -> SKU tuple."""
    rows = rows or []
    return tuple((row[0], row[1]) for row in rows if isinstance(row, list))


def serialize_strong(strong) -> Optional[list]:
    """Strong-id tuple -> JSON-safe list (None stays None)."""
    if not strong:
        return None
    return [strong[0], strong[1]]


def deserialize_strong(rows) -> Optional[tuple]:
    """JSON-safe strong-id list -> tuple, or None."""
    if not rows or not isinstance(rows, list) or len(rows) < 2:
        return None
    return (rows[0], rows[1])


# ---------------------------------------------------------------------------
# Matching against stored products
# ---------------------------------------------------------------------------

def match_offer_to_product(offer_sku: tuple, offer_strong: Optional[tuple],
                           products: dict) -> Optional[str]:
    """Return the stored product id an offer belongs to, or None.

    *products* maps product_id -> stored row ({'sku': [...], 'strong': [...]}).
    The predicate is identical to the aggregator's card-grouping predicate.
    """
    for pid, row in products.items():
        stored_sku = deserialize_sku(row.get("sku"))
        stored_strong = deserialize_strong(row.get("strong"))
        if _same_sku(offer_sku, stored_sku, offer_strong, stored_strong):
            return pid
    return None


def match_offer(offer: dict, products: dict) -> Optional[str]:
    """Convenience: compute SKU/strong for *offer* and match it to *products*."""
    return match_offer_to_product(compute_sku(offer), compute_strong(offer), products)


# ---------------------------------------------------------------------------
# Stable offer persistence identity
# ---------------------------------------------------------------------------

def make_listing_reference(strong) -> Optional[str]:
    """A stable, readable reference for a strong-id tuple, or None."""
    if not strong:
        return None
    return "/".join(str(part) for part in strong if part is not None)


def build_offer_id(offer: dict, strong: Optional[tuple]) -> str:
    """Deterministic store id for one offer.

    Priority: stable listing identity (productId / ASIN / pid+path / host+path),
    then the URL-based dedup key (same as the aggregator's offer dedup), then a
    product_key+price fallback.  Same listing re-scraped later -> same id, so
    the offer row (and its price history) is updated rather than duplicated.
    """
    from app.aggregator.aggregator import _normalize_offer_url

    platform = (offer.get("platform") or "unknown").strip().lower() or "unknown"

    ref = make_listing_reference(strong)
    if not ref:
        ref = _normalize_offer_url(offer.get("url"), offer.get("platform")) or ""
    if ref:
        return f"{platform}:{ref}"

    product_key = (offer.get("product_key") or "").strip() or "?"
    return f"{platform}:{product_key}:{offer.get('price_value')}"