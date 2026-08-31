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
