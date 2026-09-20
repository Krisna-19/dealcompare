"""
DealCompare catalog data model (Buyhatke-style foundation).

These are the persisted entities that turn the API from a "scrape on every
search" engine into a platform that accumulates a marketplace catalog over
time:

    MarketplaceSource   one marketplace (amazon / flipkart / myntra / ajio)
                        and how it is queried (official API / HTTP feed /
                        browser scrape), plus its observed health.
    Product             one canonical product/SKU grouping.  Identity is the
                        serialized SKU attribute tuple (extract_variant_
                        attributes) plus, when known, a stable marketplace
                        listing id (Flipkart productId, Amazon ASIN, ...).
    MarketplaceOffer    one store listing of a product with its current
                        price/URL/image and, critically, the verbatim source
                        record (so /search output round-trips unchanged).
    PriceSnapshot       one observed (price, timestamp) pair for an offer,
                        appended whenever the offer's price changes.

Persistence backend is the restart-safe JSON catalog (app/storage/store.py);
these models describe the shape stored there.  They are deliberately kept
separate from app/models/product_model.py, which pins the *public* /search
HTTP contract that must not change.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MarketplaceSource(BaseModel):
    """One marketplace and how the API reads it."""

    key: str                                   # "amazon", "flipkart", ...
    display_name: str                          # "Amazon", "Flipkart", ...
    kind: str                                  # "api" | "http" | "scrape" | "feed"
    enabled: bool = True
    last_seen_at: Optional[float] = None       # last attempt (any outcome)
    last_ok_at: Optional[float] = None         # last time it returned offers
    error: Optional[str] = None


class Product(BaseModel):
    """One canonical product/SKU grouping in the catalog."""

    id: str
    title: str
    category: Optional[str] = None             # detect_category label, if known
    description: Optional[str] = None          # merchant-feed copy, if provided
    brand: Optional[str] = None                # merchant-feed brand, if provided
    # Serialized canonical SKU: list of [attribute_label, value] pairs (None
    # value = attribute not stated = "unknown", never a forced split).
    sku: list[list] = []
    # Serialized strong listing identity (["asin","B0..."], ["flipkart:product_id",
    # "1002"], ["host:path", None]) or None.
    strong: Optional[list] = None
    eans: list[str] = []                       # GTIN/EAN, when sources expose it
    query_keys: list[str] = []                 # normalized queries that surfaced it
    first_seen_at: float
    updated_at: float


class MarketplaceOffer(BaseModel):
    """One persisted store listing (offer) of a product."""

    id: str
    product_id: str                            # owning Product.id in the catalog
    marketplace: str                           # display platform, "Amazon", ...
    listing_id: Optional[str] = None           # stable marketplace id, if any
    url: str
    title: str
    product_key: str
    price_value: float
    price_display: str
    image: str = ""
    original_price: Optional[float] = None     # list/MRP price, if the source states one
    availability: Optional[str] = None         # "in_stock" | "out_of_stock"; None when unknown
    feed_provenance: Optional[str] = None      # merchant-feed source, when the row came from a feed
    strong: Optional[list] = None
    sku: list[list] = []
    # The verbatim original offer dict from the scraper/API.  Kept so /search
    # can serve historically-observed offers without re-deriving anything and
    # with exactly the same field set round-tripped.
    data: dict
    first_seen_at: float
    updated_at: float


class PriceSnapshot(BaseModel):
    """One observed price for an offer at a point in time."""

    offer_id: str
    price_value: float
    observed_at: float


class CatalogDoc(BaseModel):
    """Root of the persisted catalog file."""

    version: int = 1
    sources: dict[str, MarketplaceSource] = {}
    products: dict[str, Product] = {}
    offers: dict[str, MarketplaceOffer] = {}
    snapshots: dict[str, list[PriceSnapshot]] = {}
    search_index: dict[str, dict] = {}         # query_key -> {updated_at, product_ids, offer_ids}