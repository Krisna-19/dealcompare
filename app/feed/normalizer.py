"""
Merchant-feed -> DealCompare offer-contract normalization (Phase 9).

Converts one arbitrary merchant feed row (a flat dict with whatever column
names that merchant uses) onto the existing DealCompare offer contract by
mapping the common aliases below, then passing the result through the shared
canonical annotation app.scrapers.contract.normalize_offer() -- exactly the
same canonical field set a scraper/API connector produces, so a feed offer can
be compared and matched against any marketplace offer.

Aliases accepted (first non-empty match wins; everything else is optional and
stays empty/None -- a feed that omits a field is truthful about not knowing
it, and nothing is ever fabricated):

    name / title / product_name            -> title
    description / desc / long_description  -> description (optional)
    brand / brand_name / maker             -> brand (optional)
    category / categories / product_type   -> category (optional)
    sku / product_id / product_code / ...  -> product_id (strong id ONLY when
                                              the feed genuinely supplies it)
    actual_price / original_price / mrp / list_price / striked_price
                                           -> original_price (list/MRP)
    discount_price / current_price / price / selling_price / final_price
                                           -> price_value (must be positive)
    availability / in_stock / stock_status -> availability
    url / product_url / link / product_link-> url
    image / image_url / product_image      -> image
    store / store_name / merchant / seller -> platform (defaults to the feed
                                              source when the feed omits it)
    shipping / shipping_days/delivery_days -> shipping (kept on the offer)
    coupon / coupon_code / coupon_codes    -> coupon (kept on the offer)
    currency / price_currency              -> currency (defaults to INR)
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from app.scrapers.contract import normalize_offer
from app.utils.text_utils import generate_product_key

TITLE_KEYS = ("name", "title", "product_name", "productname", "product title")
DESCRIPTION_KEYS = ("description", "desc", "long_description", "details")
BRAND_KEYS = ("brand", "brand_name", "maker")
CATEGORY_KEYS = ("category", "categories", "product_type", "department")
SKU_KEYS = (
    "sku", "product_id", "productid", "product_code", "item_code",
    "model_no", "model_number",
)
MRP_KEYS = (
    "actual_price", "original_price", "mrp", "list_price",
    "striked_price", "maximum_retail_price",
)
PRICE_KEYS = (
    "discount_price", "current_price", "price", "selling_price",
    "final_price", "offer_price", "sale_price",
)
AVAILABILITY_KEYS = ("availability", "in_stock", "stock_status", "stock", "out_of_stock")
URL_KEYS = ("url", "product_url", "link", "product_link", "productpage_url")
IMAGE_KEYS = ("image", "image_url", "imageurl", "product_image", "img")
STORE_KEYS = ("store", "store_name", "merchant", "merchant_name", "seller", "retailer")
SHIPPING_KEYS = ("shipping", "shipping_days", "delivery_days", "delivery_time")
COUPON_KEYS = ("coupon", "coupon_code", "coupon_codes", "promo_code")
CURRENCY_KEYS = ("currency", "price_currency")

CURRENCY_SYMBOLS = {
    "inr": "INR", "rs": "INR", "rs.": "INR", "rupees": "INR", "\u20b9": "INR",
    "usd": "USD", "$": "USD", "eur": "EUR", "\u20ac": "EUR", "gbp": "GBP",
    "\u00a3": "GBP",
}


def normalize_record(row: Any, source: str) -> Optional[dict]:
    """Map one feed row onto the DealCompare offer contract, or None.

    Returns None when the row carries no usable title (nothing from which a
    product identity can be derived) or is not a dict.  Unknown/missing values
    are left empty/None -- never fabricated.  The result is annotated through
    the shared canonical normalize_offer() so it behaves like any other
    connector offer (e.g. "in_stock" availability is only ever a feed's own
    stated value).
    """
    if not isinstance(row, dict):
        return None

    title = _first(row, TITLE_KEYS)
    title = _strip(title)
    if not title:
        return None

    price = _to_float(_first(row, PRICE_KEYS))
    mrp = _to_float(_first(row, MRP_KEYS))
    sku = _strip(_first(row, SKU_KEYS))
    store = _strip(_first(row, STORE_KEYS)) or source
    url = _strip(_first(row, URL_KEYS))
    image = _strip(_first(row, IMAGE_KEYS))
    availability = _normalize_availability(_first(row, AVAILABILITY_KEYS))
    currency = _normalize_currency(_first(row, CURRENCY_KEYS))

    product_key = generate_product_key(title) or ""
    offer = {
        "title": title,
        "product_key": product_key,
        "platform": store,
        "price_value": price,
        "price_display": _price_display(price),
        "url": url or "",
        "image": image or "",
        "product_id": sku or "",
        "original_price": mrp,
        "availability": availability,
        "currency": currency,
        "description": _strip(_first(row, DESCRIPTION_KEYS)) or None,
        "brand": _strip(_first(row, BRAND_KEYS)) or None,
        "category": _strip(_first(row, CATEGORY_KEYS)) or None,
        "shipping": _strip(_first(row, SHIPPING_KEYS)) or None,
        "coupon": _strip(_first(row, COUPON_KEYS)) or None,
        "source_kind": "feed",
        "captured_at": time.time(),
    }
    return normalize_offer(offer, source_kind="feed")


def _first(row: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _strip(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    return str(value).strip()


def _to_float(value: Any) -> Optional[float]:
    """Parse a price string/number to a positive float, or None.

    Accepts "₹79,999", "79999", "79,999.00", "Rs. 7999".  Currency markers are
    stripped first so an abbreviation period never becomes a decimal point.
    Zero and negative values are None: they are not a comparable price
    ("0 / pre-order" rows are marked unavailable, never persisted).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 0 else None
    text = str(value).strip()
    if not text:
        return None
    # Drop currency words/symbols (case-insensitive) so "Rs. 7999" -> " 7999"
    # and the abbreviation's period is not read as a decimal point.
    text = re.sub(r"(?i)(?:rs\.?|inr\.?|usd\.?|eur\.?|gbp\.?|rupees?)", "", text)
    text = text.replace("\u20b9", "").replace("$", "").replace("\u20ac", "").replace("\u00a3", "")
    cleaned = re.sub(r"[^0-9.]", "", text)
    if not cleaned or cleaned == ".":
        return None
    # More than one dot means thousands separators, not decimals.
    if cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return number if number > 0 else None


def _price_display(price: Optional[float]) -> str:
    if not price or price <= 0:
        return ""
    return f"\u20b9{int(price):,}"


def _normalize_currency(value: Any) -> str:
    if value is None:
        return "INR"
    if isinstance(value, bool):
        return "INR"
    token = str(value).strip().lower()
    if not token:
        return "INR"
    return CURRENCY_SYMBOLS.get(token, token.upper()[:3])


def _normalize_availability(value: Any) -> Optional[str]:
    """Map a feed's availability statement onto in_stock/out_of_stock.

    Only a feed's own explicit statement is trusted: anything else stays None
    (unknown) so a strict match can never be seeded by an invented value.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "in_stock" if value else "out_of_stock"
    token = re.sub(r"[^a-z0-9 ]", " ", str(value).lower())
    token = " ".join(token.split())
    if token in ("1", "true", "yes", "in stock", "instock", "available", "in"):
        return "in_stock"
    if token in ("0", "false", "no", "out of stock", "outofstock", "oos",
                 "unavailable", "sold out", "not available", "out"):
        return "out_of_stock"
    return None