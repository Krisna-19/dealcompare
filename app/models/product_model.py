from typing import Optional

from pydantic import BaseModel, Field


class Product:
    def __init__(
        self,
        title: str,
        platform: str,
        price_value: float,
        price_display: str,
        url: str,
        rating: Optional[float] = None,
        image: Optional[str] = ""
    ):
        self.title = title
        self.platform = platform
        self.price_value = price_value
        self.price_display = price_display
        self.url = url
        self.rating = rating
        self.image = image


# ---------------------------------------------------------------------------
# Typed /search response contract.
#
# These models are wired into FastAPI via `response_model` on the /search
# endpoint so the published response shape is enforced and machine-readable
# (OpenAPI).  `image` defaults keep the schema stable even when a store
# returned no image for an offer/card.
# ---------------------------------------------------------------------------


class Offer(BaseModel):
    """One store offer inside a product card."""

    title: str
    product_key: str
    platform: str
    price_value: float
    price_display: str
    url: str
    image: str = ""


class ProductCard(BaseModel):
    """One canonical product grouping with its best (cheapest) offer."""

    title: str
    best_price: str
    best_platform: str
    best_url: str
    image: str = ""
    offers: list[Offer] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """The complete /search response envelope."""

    message: str
    category: str
    results: list[ProductCard] = Field(default_factory=list)


class PricePoint(BaseModel):
    """One persisted price observation for a single offer (never derived)."""

    price_value: float
    observed_at: float                         # unix epoch seconds


class PriceHistoryOffer(BaseModel):
    """Real price history for EXACTLY ONE persisted marketplace listing.

    Each offer row in the catalog is one marketplace listing (one store, one
    SKU/variant).  A response may contain several of these (e.g. the Amazon
    and Flipkart listings of one product), but the snapshots of one offer are
    never merged into another's — cross-store / variant mixing is impossible
    by construction.
    """

    product_key: str
    platform: str                              # marketplace display name
    title: str
    url: str
    image: str = ""
    current_price: Optional[float] = None      # latest persisted price, if any
    observations: list[PricePoint] = Field(default_factory=list)  # chronological


class PriceHistoryResponse(BaseModel):
    """The complete GET /products/{product_key}/price-history envelope."""

    product_key: str
    catalog_enabled: bool = True
    offers: list[PriceHistoryOffer] = Field(default_factory=list)
