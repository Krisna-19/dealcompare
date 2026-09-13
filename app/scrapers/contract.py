"""
Cross-marketplace offer contract (Phase G).

Every marketplace connector still emits the *base* shareable shape that the
aggregator, catalog and frontend are built on:

    {
        "title":         str,   # product title as shown on the source
        "product_key":   str,   # grouping key (brand-model-storage)
        "platform":      str,   # display name, e.g. "Amazon", "Flipkart"
        "price_value":   float,
        "price_display": str,   # formatted price, e.g. "₹79,999"
        "url":           str,   # full product page URL
        "image":         str,   # product image URL (optional)
    }

The aggregator, catalog store and HTTP response model only read those fields,
so adding *extra* canonical keys is safe: pydantic response models
(app/models/product_model.py) strip unknown keys at the HTTP boundary, and the
catalog keeps the dict as-is.

normalize_offer() annotates a copy of an offer with the explicit, comparable
canonical name set so any two connectors can be compared / matched across
marketplaces on spelling, not invention:

    marketplace              == platform (same value, canonical name)
    marketplace_product_id   == source's own identity (Flipkart PID, Myntra
                               product ID, Amazon ASIN) — "" when unknown
    title                    == title
    price                    == price_value (canonical numeric price)
    original_price           == list/MRP price when the source reports one
                               (Flipkart maximumRetailPrice, Myntra mrp,
                               Amazon offersV2 savingBasis) — None when unknown
    currency                 == "INR" (each source is India-first)
    availability             == "in_stock" | "out_of_stock"; None when unknown
    product_url              == url (canonical name of the product link)
    image_url                == image (canonical name of the image link)
    product_key              == product_key
    captured_at              == unix timestamp the offer was observed
    source_kind              == "api" | "http" | "scrape" | "deferred"

Sources that already expose a richer field (e.g. product_id) keep them; the
canonical copy never deletes data.  Failure discipline is unchanged: sources
never fabricate original_price / availability / ids — missing values stay
empty/None so a strict match can never be seeded by a guessed value.
"""

from __future__ import annotations

import time


def normalize_offer(offer: dict, source_kind: str = "") -> dict:
    """Return a copy of *offer* with the canonical comparison fields attached.

    The original offer is never mutated.  Unknown/missing extras are left
    empty ("" / None) so downstream matches can never rely on fabricated data.
    """
    if not isinstance(offer, dict):
        return offer

    canonical = dict(offer)

    canonical["marketplace"] = offer.get("platform", "")
    canonical["marketplace_product_id"] = offer.get("product_id") or ""
    canonical["price"] = float(offer.get("price_value", 0) or 0)
    canonical["product_url"] = offer.get("url", "")

    original = offer.get("original_price")
    canonical["original_price"] = (
        float(original) if isinstance(original, (int, float)) and original > 0 else None
    )

    currency = offer.get("currency")
    if isinstance(currency, str) and currency.strip():
        canonical["currency"] = currency.strip().upper()
    else:
        canonical["currency"] = "INR"

    availability = offer.get("availability")
    if availability in ("in_stock", "out_of_stock"):
        canonical["availability"] = availability
    else:
        canonical["availability"] = None

    canonical["image_url"] = offer.get("image", "")

    if offer.get("captured_at") is None:
        canonical["captured_at"] = time.time()
    else:
        canonical["captured_at"] = offer["captured_at"]

    if offer.get("source_kind") is None:
        canonical["source_kind"] = (source_kind or "").strip()
    else:
        canonical["source_kind"] = offer["source_kind"]

    return canonical