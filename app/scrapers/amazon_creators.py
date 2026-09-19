"""
Amazon Creators API adapter (Phase D) — official product data via the
Amazon Creators API (the successor to Product Advertising API 5, which was
deprecated on 2026-05-15).

Endpoints (verified against the public Creators API documentation):
    Token:      POST {amazon_creators_token_url}
                Content-Type: application/json
                Body (JSON):  {
                    "grant_type": "client_credentials",
                    "client_id":     <client id>,
                    "client_secret": <client secret>,
                    "scope":         "creatorsapi::default"
                }
                -> {"access_token": "...", ...}  (token cached until expiry)

    SearchItems: POST {amazon_creators_api_base_url}/catalog/v1/searchItems
                Headers: Authorization: Bearer <token>
                         x-marketplace: www.amazon.in
                Body (JSON): {
                    "partnerTag": <partner tag>,
                    "keywords":   <query>,
                    "itemCount":  <n>,
                    "resources": [
                        "images.primary.large",
                        "itemInfo.title",
                        "offersV2.listings.availability",
                        "offersV2.listings.price",
                        "offersV2.listings.merchantInfo"
                    ]
                }
                -> {"searchResult": {"items": [
                    {
                        "asin": "...",
                        "detailPageURL": "...",
                        "images":  {"primary": {"large": {"url": "..."}}},
                        "itemInfo": {"title": {"displayValue": "..."}},
                        "offersV2": {"listings": [
                            {
                                "availability": {"type": "IN_STOCK", ...},
                                "price": {
                                    "money":        {"amount", "currency",
                                                     "displayAmount"},
                                    "savingBasis":  {"money": {...}}  # list price
                                },
                                "merchantInfo": {...}
                            }
                        ]}
                    }
                ]}}

    GetItems (used when a search item arrives without an offer, i.e. "when
    needed"):  POST {base}/catalog/v1/getItems  with body itemIds=[asin] and
    the same headers/resources; the response nests items as a LIST under
    `itemResults.items` (each dict carrying an "asin" field — the documented
    shape; Amazon's cURL guide renders the container as "itemsResult").  The
    adapter looks the requested ASIN up by that field.

Normalisation map to the shared DealCompare contract:
    title            <- itemInfo.title.displayValue
    product_id/asin  <- item.asin
    price_value      <- preferred listing price.money.amount (INR on amazon.in)
    original_price   <- price.savingBasis.money.amount (list price) when higher
    availability     <- listing availability.type ("in_stock" when buyable)
    url              <- detailPageURL
    image            <- images.primary.large.url
    source_kind      <- "api"

Failure / safety contract:
  - Enabled only when AMAZON_DATA_SOURCE=api AND client id/secret/partner tag
    are all configured; otherwise the adapter returns [] immediately.
  - Any token/eligibility/network/non-200/parse failure returns [] (honest
    empty).  Never survives on the old Playwright scraper and never fabricates
    products, prices, or availability.
  - Account NOT eligible for this account (HTTP 403/eligibility errors) simply
    yields [] — the source is deferred, never faked.
"""

from __future__ import annotations

import logging
import threading
import time

import requests

from app.core.config import get_settings
from app.scrapers.contract import normalize_offer
from app.services.ranking_service import calculate_match_score
from app.utils.text_utils import generate_product_key

logger = logging.getLogger(__name__)

# Creators API resources the adapter requests for every item.  offersV2.listing
# is what carries price + availability; offersV2 LIST_PRICE / other resource
# names are intentionally NOT requested so the response stays small.
_CATALOG_RESOURCES = [
    "images.primary.large",
    "itemInfo.title",
    "offersV2.listings.availability",
    "offersV2.listings.price",
    "offersV2.listings.merchantInfo",
]

_SEARCH_ITEMS_PATH = "/catalog/v1/searchItems"
_GET_ITEMS_PATH = "/catalog/v1/getItems"

# Availability types that mean a product can actually be bought.  Missing
# availability is treated as in-stock (same convention as the Flipkart API
# adapter) so a search item that omits the field is not dropped.
_IN_STOCK_TYPES = {"IN_STOCK", "AVAILABLE", "NOW"}
_OUT_OF_STOCK_TYPES = {"OUT_OF_STOCK", "STATUS_UNAVAILABLE", "LIQUIDATION"}

_TOKEN_CACHE = {"access_token": None, "expires_at": 0.0}
_TOKEN_LOCK = threading.Lock()


def clear_token_cache():
    """Drop any cached access token (used by tests)."""
    with _TOKEN_LOCK:
        _TOKEN_CACHE["access_token"] = None
        _TOKEN_CACHE["expires_at"] = 0.0


# ---------------------------------------------------------------------------
# Configuration / enablement
# ---------------------------------------------------------------------------

def api_credentials_available() -> bool:
    """True only when the three Creators API values are configured."""
    settings = get_settings()
    return bool(
        (settings.amazon_creator_client_id or "").strip()
        and (settings.amazon_creator_client_secret or "").strip()
        and (settings.amazon_partner_tag or "").strip()
    )


def api_enabled() -> bool:
    """True only when AMAZON_DATA_SOURCE=api AND all credentials exist."""
    settings = get_settings()
    return (
        settings.amazon_data_source.strip().lower() == "api"
        and api_credentials_available()
    )


# ---------------------------------------------------------------------------
# OAuth2 token flow (LwA client-credentials for the Creators API)
# ---------------------------------------------------------------------------

def _request_access_token():
    """
    Perform the LwA client-credentials token request.

    Returns the raw API response dict (or None on any failure), including the
    `access_token` for a successful call.  Never raises.
    """
    settings = get_settings()
    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.amazon_creator_client_id.strip(),
        "client_secret": settings.amazon_creator_client_secret.strip(),
        "scope": settings.amazon_creators_scope.strip() or "creatorsapi::default",
    }
    try:
        resp = requests.post(
            settings.amazon_creators_token_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=getattr(settings, "amazon_creators_timeout_seconds", 8.0),
        )
    except requests.exceptions.RequestException as e:
        logger.warning("Amazon Creators token request failed: %s", e)
        return None

    if resp.status_code != 200:
        logger.warning("Amazon Creators token endpoint returned HTTP %s", resp.status_code)
        return None

    try:
        return resp.json()
    except ValueError:
        logger.warning("Amazon Creators token endpoint returned invalid JSON")
        return None


def _get_access_token():
    """Return a valid cached access token, fetching a fresh one when needed."""
    with _TOKEN_LOCK:
        if _TOKEN_CACHE["access_token"] and time.time() < _TOKEN_CACHE["expires_at"]:
            return _TOKEN_CACHE["access_token"]

    data = _request_access_token()
    if not data or not data.get("access_token"):
        return None

    expires_in = float(data.get("expires_in") or 3600)
    with _TOKEN_LOCK:
        _TOKEN_CACHE["access_token"] = data["access_token"]
        # Refresh a little early so requests never race a just-expired token.
        _TOKEN_CACHE["expires_at"] = time.time() + max(60.0, expires_in - 60)
    return data["access_token"]


# ---------------------------------------------------------------------------
# Catalog API requests (POST JSON, bearer auth, x-marketplace header)
# ---------------------------------------------------------------------------

def _catalog_headers(token: str) -> dict:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-marketplace": settings.amazon_marketplace.strip() or "www.amazon.in",
    }


def _catalog_body(**extra) -> dict:
    """Base JSON body: partnerTag + marketplace + resources, then caller's fields.

    `marketplace` is a REQUIRED request parameter on every Creators API call
    (checked against the Common Request Headers and Parameters doc) and
    travels here as well as in the x-marketplace header.
    """
    settings = get_settings()
    return {
        "partnerTag": settings.amazon_partner_tag.strip(),
        "marketplace": settings.amazon_marketplace.strip() or "www.amazon.in",
        "resources": list(_CATALOG_RESOURCES),
        **extra,
    }


def _catalog_request(path: str, token: str, body: dict):
    """
    POST one Creators catalog request and return the JSON response dict.

    Returns None on any failure (non-200, network error, invalid JSON) — the
    caller treats None as honest empty.  Never raises.
    """
    settings = get_settings()
    url = settings.amazon_creators_api_base_url.rstrip("/") + path
    try:
        resp = requests.post(
            url,
            json=body,
            headers=_catalog_headers(token),
            timeout=getattr(settings, "amazon_creators_timeout_seconds", 8.0),
        )
    except requests.exceptions.RequestException as e:
        logger.warning("Amazon Creators request %s failed: %s", path, e)
        return None

    if resp.status_code != 200:
        logger.warning("Amazon Creators %s returned HTTP %s", path, resp.status_code)
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.warning("Amazon Creators %s returned invalid JSON", path)
        return None
    return data if isinstance(data, dict) else None


def _request_search_items(query: str, token: str):
    """SearchItems call for *query* -> {"searchResult": {...}} or None."""
    settings = get_settings()
    body = _catalog_body(
        keywords=query,
        itemCount=max(1, int(getattr(settings, "amazon_creators_result_count", 10))),
    )
    return _catalog_request(_SEARCH_ITEMS_PATH, token, body)


def _request_get_items(asins, token: str):
    """GetItems call for *asins* -> {"itemResults": {"items": [...]}} or None."""
    if not asins:
        return None
    body = _catalog_body(itemIds=[a for a in asins if a])
    return _catalog_request(_GET_ITEMS_PATH, token, body)


def _item_from_get_items_response(data, asin: str):
    """Find one item in a GetItems response by its ASIN field.

    The documented response nests items as a LIST under `itemResults.items`
    (each dict carrying "asin"); Amazon's cURL guide renders the same
    container as "itemsResult".  Both spellings are read and the requested
    ASIN is matched by its field value (the ordering of items in the response
    is not guaranteed, so positional lookup is never used).
    """
    if not isinstance(data, dict) or not asin:
        return None
    container = data.get("itemResults")
    if not isinstance(container, dict):
        container = data.get("itemsResult")
    items = (container or {}).get("items") if isinstance(container, dict) else None
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and str(item.get("asin") or "").strip() == asin:
            return item
    return None


# ---------------------------------------------------------------------------
# OffersV2 -> offer normalisation
# ---------------------------------------------------------------------------

def _money_amount(obj):
    """Extract a positive float amount from an offersV2 money object, else 0."""
    if not isinstance(obj, dict):
        return 0.0
    amount = obj.get("amount")
    try:
        value = float(amount) if amount is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def _listing_price(listing):
    """(selling, original) amounts for one offersV2 listing.

    `price.money` is the offer price; `price.savingBasis.money` is the
    comparison/list price (the original_price of the contract).  The original
    is only surfaced when it is strictly above the selling price.
    """
    price_obj = (listing.get("price") or {}) if isinstance(listing, dict) else {}
    selling = _money_amount(price_obj.get("money"))
    saving = _money_amount((price_obj.get("savingBasis") or {}).get("money"))
    original = saving if saving > selling else 0.0
    return selling, original


def _listing_buyable(listing) -> bool:
    """A listing is a valid comparable offer when it is in stock and priced."""
    avail_type = ((listing.get("availability") or {}) or {}).get("type") or ""
    if isinstance(avail_type, str):
        if avail_type in _OUT_OF_STOCK_TYPES:
            return False
        if avail_type and avail_type not in _IN_STOCK_TYPES:
            return False  # unknown -> treat as not buyable
    selling, _ = _listing_price(listing)
    return selling > 0


def _preferred_listing(item):
    """Pick the buyable offersV2 listing to price the item from.

    Prefers the buy-box winner (buyingOptionsMetadata.isPreferredAvailable)
    and otherwise the first buyable listing.  Returns the listing dict or None.
    """
    listings = ((item.get("offersV2") or {}).get("listings")) or []
    if not isinstance(listings, list):
        return None
    buyable = [l for l in listings if isinstance(l, dict) and _listing_buyable(l)]
    for listing in buyable:
        meta = (listing.get("buyingOptionsMetadata") or {}).get("isPreferredAvailable")
        if meta:  # buy-box winner
            return listing
    return buyable[0] if buyable else None


def _extract_item(item):
    """
    Convert one Creators API item into a DealCompare offer, or None.

    Skips items with no usable title/URL/price — never fabricates any of them.
    """
    if not isinstance(item, dict):
        return None

    asin = (item.get("asin") or "").strip() or None
    title = ((item.get("itemInfo") or {}).get("title") or {}).get("displayValue")
    title = (title or "").strip()
    if not title:
        return None

    detail_page_url = (item.get("detailPageURL") or "").strip()
    if not detail_page_url:
        if asin:
            settings = get_settings()
            marketplace = settings.amazon_marketplace.strip() or "www.amazon.in"
            detail_page_url = f"https://{marketplace}/dp/{asin}"
        else:
            return None

    image = ((item.get("images") or {}).get("primary") or {}).get(
        "large", {}
    ).get("url") or ""

    listing = _preferred_listing(item)
    if listing is None:
        # Defer to GetItems refinement (the item had no usable offer here).
        return None

    selling, original = _listing_price(listing)

    product_key = generate_product_key(title)
    if not product_key:
        return None

    offer = {
        "title": title,
        "product_key": product_key,
        "platform": "Amazon",
        "price_value": float(selling),
        "price_display": f"\u20b9{int(selling):,}",
        "url": detail_page_url,
        "image": image or "",
        "product_id": asin,
        "original_price": original if original > 0 else None,
        "currency": "INR",
        "availability": "in_stock",
        "source_kind": "api",
    }
    return normalize_offer(offer, "api")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_items(asin: str):
    """
    Look up a single ASIN via GetItems.

    Returns a normalized DealCompare offer (list with one dict) or [] when the
    item has no usable offer.  Also available to future detail-view lookups.
    """
    if not asin or not api_enabled():
        return []
    token = _get_access_token()
    if not token:
        return []
    data = _request_get_items([asin], token)
    if not data:
        return []
    item = _item_from_get_items_response(data, asin)
    offer = _extract_item(item)
    return [offer] if offer else []


def search_amazon_creators(query: str):
    """
    Search Amazon (www.amazon.in) via the official Creators API.

    Uses SearchItems for query results; any item that arrives without a usable
    offer is re-fetched through GetItems (one bounded call) so "GetItems when
    needed" is exercised.  Applies the shared match-score gate and the
    max_results_per_platform cap, exactly like every other connector.

    Returns:
        list[dict]: Normalised DealCompare offers.  On any failure — missing
        credentials, not eligible, non-200, network error, invalid/empty
        payload — returns [] (honest empty).  Never fabricates products.
    """
    if not api_enabled():
        logger.info("Amazon Creators API not enabled (AMAZON_DATA_SOURCE/api + credentials)")
        return []

    token = _get_access_token()
    if not token:
        return []

    data = _request_search_items(query, token)
    items = ((data or {}).get("searchResult") or {}).get("items")
    if not isinstance(items, list):
        return []

    settings = get_settings()
    results = []
    missing = []

    for item in items:
        if not isinstance(item, dict):
            continue
        offer = _extract_item(item)
        if offer is not None:
            results.append(offer)
        elif item.get("asin"):
            missing.append(item["asin"])

    # GetItems refinement: exactly one call for search items that had no offer,
    # "when needed" — deterministically bounded, never a loop.
    if missing:
        refill = _request_get_items(missing, token)
        if refill:
            for offer_asin in missing:
                offer = _extract_item(
                    _item_from_get_items_response(refill, offer_asin)
                )
                if offer is not None:
                    results.append(offer)

    accepted = []
    for offer in results:
        title = offer["title"]
        if len(title.split()) < 3:
            continue
        score = calculate_match_score(query, title)
        if score < settings.match_score_threshold:
            continue
        accepted.append(offer)
        if len(accepted) >= settings.max_results_per_platform:
            break

    logger.info("Amazon Creators API returned: %d results", len(accepted))
    return accepted