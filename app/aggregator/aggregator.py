# -----------------------------
# AGGREGATE PRODUCTS
# -----------------------------
import re
from urllib.parse import urlparse, unquote, parse_qs

from app.utils.text_utils import extract_variant_attributes

_AMAZON_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})", re.IGNORECASE)

# Order is significant: canonical SKU attributes used for grouping.
_KEY_LABELS = (
    "brand", "model", "ram", "storage", "processor", "color", "edition", "model_no",
    "product_type", "pack_count", "size_cm",
)


def _normalize_offer_url(url, platform):
    """
    Reduce an offer URL to a stable per-product key used for OFFER
    DEDUPLICATION (dropping truly identical scraper records).

    Live storefront URLs are full of tracking / personalisation noise
    (amazon dib/gid/simid, sspa click wrappers, flipkart qid/iid/srno...).
    Two scraper records pointing at the *same* listing must share a key so
    duplicates can be removed, while distinct listings (different Amazon
    ASIN, different Flipkart slug+pid) must produce different keys.
    """
    if not url:
        return None
    u = str(url).strip()
    if not u:
        return None

    fp = platform.lower() if platform else ""

    # Amazon sponsored ("sspa/click") links wrap the real /dp/ path inside a
    # percent-encoded query value, so scan the fully-decoded URL for the ASIN.
    if fp == "amazon":
        m = _AMAZON_ASIN_RE.search(unquote(u))
        if m:
            return f"asin:{m.group(1).upper()}"

    # Flipkart DOM-fallback offers are relative URLs.
    if u.startswith("/") and fp == "flipkart":
        u = "https://www.flipkart.com" + u

    parsed = urlparse(u)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if "flipkart" in host:
        # pid is the stable product identifier; tracking params (qid/iid/
        # srno/ssid) must NOT be part of the identity.
        pid = (parse_qs(parsed.query).get("pid") or [None])[0]
        base = f"flipkart:{path.rstrip('/')}"
        return f"{base}?pid={pid}" if pid else base

    m = _AMAZON_ASIN_RE.search(path)
    if m:
        return f"asin:{m.group(1).upper()}"

    return f"{host}:{path.rstrip('/')}".lower()


def _strong_platform_id(url, platform):
    """
    Stable identifier of the exact source listing (Amazon ASIN, Flipkart
    pid+path, or host+path).  Two offers sharing a strong id belong to the
    same listing/page even when their titles describe selectable variants
    (e.g. one Amazon ASIN sold in multiple colours).
    """
    if not url:
        return None
    u = str(url).strip()
    if not u:
        return None

    fp = platform.lower() if platform else ""

    if fp == "amazon":
        m = _AMAZON_ASIN_RE.search(unquote(u))
        if m:
            return ("asin", m.group(1).upper())

    if fp == "flipkart":
        if u.startswith("/"):
            u = "https://www.flipkart.com" + u
        parsed = urlparse(u)
        pid = (parse_qs(parsed.query).get("pid") or [None])[0]
        base = f"flipkart:{parsed.path.rstrip('/')}"
        return (base, pid) if pid else (base, None)

    parsed = urlparse(u)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    m = _AMAZON_ASIN_RE.search(path)
    if m:
        return ("asin", m.group(1).upper())
    return (f"{host}:{path.rstrip('/')}".lower(), None)


def _sku_key(attrs, product):
    """
    Canonical identity of the actual product/SKU described by an offer.

    Built from the variant-defining attributes parsed out of the title
    (brand, model incl. FE/Ultra/Pro, RAM, storage, processor, colour,
    edition, model number).  A missing attribute is encoded as None and is
    treated as *unknown* when matching — it never forces a split and never
    invents a difference.  Every attribute is retained positionally so two
    offers can be compared attribute-by-attribute regardless of which
    retailer chose to state (or omit) each value.

    For products with no detectable attributes the provided product_key is
    used as a fallback so generic, attribute-less items still group.
    """
    parts = [(label, attrs.get(label)) for label in _KEY_LABELS]
    if any(value for _, value in parts):
        return tuple(parts)

    fallback = (product.get("product_key") or product.get("title") or "").strip().lower()
    return (("key", fallback),)


def _is_fallback_key(sku):
    """True when a SKU has no detectable attributes (only a fallback key)."""
    return bool(sku) and sku[0][0] == "key"


def _attrs_match(sku_a, sku_b, skip_color=False):
    """
    Attribute-compatible match between two canonical SKUs.

    - Every attribute both listings EXPLICITLY state must agree.
    - An attribute one listing omits (None) is UNKNOWN and never a conflict,
      so "S24 Onyx Black 128 GB" and "S24 Onyx Black 128 GB 8GB RAM" are the
      same SKU when a known S24 variant fixes the RAM as 8GB.
    - skip_color: ignore the colour attribute (used for the same-listing
      case, where one product page legitimately offers selectable colours).
    """
    for (label_a, value_a), (label_b, value_b) in zip(sku_a, sku_b):
        if skip_color and label_a == "color":
            continue
        if value_a is None or value_b is None:
            continue
        if value_a != value_b:
            return False
    return True


def _same_sku(sku_a, sku_b, strong_a, strong_b):
    """
    Two offers belong to the same product card when their stated product
    attributes are compatible — the identical SKU (attribute match) OR the
    identical source listing (shared strong platform id; a single listing
    may present several colours, but hard attributes must still agree).
    Products with no detectable attributes only merge on an exact fallback
    key.
    """
    if _is_fallback_key(sku_a) or _is_fallback_key(sku_b):
        return sku_a == sku_b
    if strong_a and strong_a == strong_b:
        return _attrs_match(sku_a, sku_b, skip_color=True)
    return _attrs_match(sku_a, sku_b, skip_color=False)


def _offer_identity(product):
    """A duplicate-safe identity for one offer inside its product group."""
    platform = (product.get("platform") or "").strip().lower()
    price = product.get("price_value")
    normalized = _normalize_offer_url(product.get("url"), product.get("platform"))

    if normalized is None:
        # No URL: fall back to the available fields so same-store, same
        # variant at the same price is still recognised as a duplicate.
        attrs = extract_variant_attributes(product.get("title") or "")
        return (
            platform,
            _sku_key(attrs, product),
            (product.get("title") or "").strip().lower(),
            price,
        )
    return (platform, normalized, price)


def _deduplicate_offers(items):
    """Drop exact duplicate offers, preserving the first occurrence order."""
    deduped = []
    seen = set()
    for product in items:
        identity = _offer_identity(product)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(product)
    return deduped


def aggregate_products(products):

    # Entries without a usable price (placeholder/unparsed rows) must
    # never become the best offer or be shown as comparable offers.
    valid = []
    for product in products:
        key = product.get("product_key")
        if not key:
            continue
        price = product.get("price_value")
        if not price or price <= 0:
            continue
        valid.append(product)

    # Cluster offers into product cards by SKU identity (and same-listing
    # evidence), preserving input order: the first offer of a card defines it,
    # later offers join an existing card only when they match its SKU.
    groups = []
    representatives = []

    for product in valid:
        attrs = extract_variant_attributes(product.get("title") or "")
        sku = _sku_key(attrs, product)
        strong = _strong_platform_id(product.get("url"), product.get("platform"))

        matched = None
        for gi, rep in enumerate(representatives):
            rep_attrs = extract_variant_attributes(rep.get("title") or "")
            if _same_sku(
                sku,
                _sku_key(rep_attrs, rep),
                strong,
                _strong_platform_id(rep.get("url"), rep.get("platform")),
            ):
                matched = gi
                break

        if matched is None:
            representatives.append(product)
            groups.append([product])
        else:
            groups[matched].append(product)

    results = []

    for items in groups:

        # Deduplicate before selecting the best offer so the Lowest badge
        # and offers list always reflect the remaining, unique offers.
        offers = _deduplicate_offers(items)

        best = min(offers, key=lambda x: x["price_value"] if x["price_value"] else float("inf"))

        results.append({
            "title": best["title"],
            "best_price": best["price_display"],
            "best_platform": best["platform"],
            "best_url": best["url"],
            "offers": offers
        })

    return results