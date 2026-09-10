import json
import logging

import requests

from app.core.config import get_settings
from app.services.ranking_service import calculate_match_score
from app.utils.text_utils import generate_product_key

"""
Flipkart Affiliate search API adapter — real product data from the official
Flipkart Affiliate API (https://affiliate.flipkart.com/api-docs/).

This module implements the officially documented search endpoint and
normalises its response into the shared DealCompare product contract, so the
Affiliate API can replace/augment the Playwright scraper for e-commerce data.

API contract (verified against the official docs / account page):
    GET {base}/{format:1.0}/search.{format:json}?query=<q>&resultCount=<n>
    Headers:
        Fk-Affiliate-Id:    <Affiliate Tracking ID>
        Fk-Affiliate-Token: <Affiliate API Token>
    Params:
        query         -- free-text search query (required)
        resultCount   -- number of results (documented max 10, no pagination)
    Limit:
        ~20 requests/second per Affiliate ID.
    Success response shape (JSON v1.0):
        {
          "productInfoList": [
            {
              "productBaseInfoV1": {
                "productId", "title",
                "imageUrls": {"200x200": ..., "800x800": ...},
                "maximumRetailPrice":      {"amount": float, "currency": "INR"},
                "flipkartSellingPrice":    {"amount": float, "currency": "INR"},
                "flipkartSpecialPrice":    {"amount": float, "currency": "INR"},
                "productUrl", "productBrand",
                "isAvailable": bool, "inStock": bool, "categoryPath"
              },
              "categorySpecificInfoV1": {...}
            }
          ]
        }

Failure contract:
    - Like every source, this never fabricates products or prices.  On any
      error it returns [] (honest empty) so the caller can fall back to the
      Playwright scraper or report an empty source.
    - A missing/empty response, a non-200 status, or any parse failure all
      yield [].
"""

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

def build_api_search_url(query: str, result_count: int = None) -> str:
    """Build the official Flipkart Affiliate search JSON URL for *query*.

    Uses the configured base URL and result count.  No credentials are
    embedded in the URL (they travel as headers).
    """
    settings = get_settings()
    base = settings.flipkart_api_base_url.rstrip("/")
    count = result_count or getattr(settings, "flipkart_api_result_count", 10)
    return (
        f"{base}/search.json"
        f"?query={requests.utils.quote(query)}"
        f"&resultCount={int(count)}"
    )


def api_credentials_available() -> bool:
    """True only when both Affiliate credentials are configured."""
    settings = get_settings()
    return bool(
        (settings.flipkart_affiliate_id or "").strip()
        and (settings.flipkart_affiliate_token or "").strip()
    )


def api_enabled() -> bool:
    """True only when the API data source is selected AND credentials exist."""
    settings = get_settings()
    return (
        settings.flipkart_data_source.strip().lower() == "api"
        and api_credentials_available()
    )


# ---------------------------------------------------------------------------
# Normalisation  (raw API entry -> DealCompare product dict)
# ---------------------------------------------------------------------------

def _price_amount(price_obj):
    """Extract a float amount from a {amount, currency} price object."""
    if not isinstance(price_obj, dict):
        return 0.0
    amount = price_obj.get("amount")
    if amount is None:
        return 0.0
    try:
        return float(amount)
    except (TypeError, ValueError):
        return 0.0


def _normalise_api_product(raw):
    """
    Convert one API productInfo entry into the DealCompare product dict.

    Returns None if the entry is unusable (no title or no URL), so the caller
    can skip it.  Prices: Flipkart's consumer-facing price is the
    flipkartSellingPrice; falling back to the special price and then the MRP
    mirrors how the scraper surfaces a usable price.
    """
    if not isinstance(raw, dict):
        return None

    base = raw.get("productBaseInfoV1")
    if not isinstance(base, dict):
        return None

    title = (base.get("title") or "").strip()
    if not title:
        return None

    # --- price ---
    price_value = _price_amount(base.get("flipkartSellingPrice"))
    if price_value <= 0:
        price_value = _price_amount(base.get("flipkartSpecialPrice"))
    if price_value <= 0:
        price_value = _price_amount(base.get("maximumRetailPrice"))

    if price_value and price_value > 0:
        price_display = f"\u20b9{int(price_value):,}"
    else:
        price_value = 0
        price_display = "Check price"

    # --- url ---
    url = (base.get("productUrl") or "").strip()
    if not url:
        return None

    # --- productId: stable Flipkart identity for the grouping pipeline ---
    product_id = (base.get("productId") or "").strip() or None

    # --- stock status: out-of-stock products are not valid comparable offers ---
    in_stock = base.get("inStock")
    is_available = base.get("isAvailable")
    # Treat explicit False as out-of-stock; missing/None treated as in-stock
    # (some products omit the field).
    if in_stock is False or is_available is False:
        return None

    # --- image: prefer the largest documented thumbnail ---
    image = ""
    image_urls = base.get("imageUrls")
    if isinstance(image_urls, dict):
        for key in ("800x800", "400x400", "200x200"):
            if image_urls.get(key):
                image = image_urls[key]
                break

    product_key = generate_product_key(title)
    if not product_key:
        return None

    return {
        "title": title,
        "product_key": product_key,
        "platform": "Flipkart",
        "price_value": float(price_value),
        "price_display": price_display,
        "url": url,
        "image": image,
        "product_id": product_id,
    }


# ---------------------------------------------------------------------------
# Request / response handling
# ---------------------------------------------------------------------------

def _parse_search_response(text):
    """Parse the API JSON body into a list of raw product entries ([] if bad)."""
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        logger.warning("Flipkart API returned invalid JSON")
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("productInfoList")
    if not isinstance(entries, list):
        if entries is not None:
            logger.warning("Flipkart API productInfoList is not a list")
        return []
    return [e for e in entries if isinstance(e, dict)]


def _request_search(query: str):
    """
    Perform the authenticated Affiliate API GET request.

    Returns the raw response body text on HTTP 200, otherwise None.  Raises
    nothing — network/protocol errors are converted to None so the caller can
    fall back cleanly.
    """
    settings = get_settings()
    url = build_api_search_url(query)

    headers = {
        "Fk-Affiliate-Id": settings.flipkart_affiliate_id.strip(),
        "Fk-Affiliate-Token": settings.flipkart_affiliate_token.strip(),
    }

    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=getattr(settings, "flipkart_api_timeout_seconds", 8.0),
        )
    except requests.exceptions.RequestException as e:
        logger.warning("Flipkart API request failed: %s", e)
        return None

    if resp.status_code != 200:
        logger.warning(
            "Flipkart API returned HTTP %s for query", resp.status_code
        )
        return None

    return resp.text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_flipkart_api(query: str):
    """
    Search Flipkart via the official Affiliate API.

    Returns:
        list[dict]: Normalised DealCompare product dicts matching the shared
        contract (same fields as the scraper).  On any failure — missing
        credentials, network error, non-200, invalid/empty payload — returns
        [] (honest empty).  Never fabricates products or prices.
    """
    settings = get_settings()
    raw_products = _parse_search_response(_request_search(query))
    if not raw_products:
        return []

    results = []
    for raw in raw_products:
        normalised = _normalise_api_product(raw)
        if not normalised:
            continue

        title = normalised["title"]
        if len(title.split()) < 2:
            continue

        score = calculate_match_score(query, title)
        if score < settings.match_score_threshold:
            continue

        results.append(normalised)

        if len(results) >= settings.max_results_per_platform:
            break

    logger.info("Flipkart API returned: %d results", len(results))
    return results
