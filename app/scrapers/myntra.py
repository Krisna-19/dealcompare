"""
Myntra scraper — real product data from myntra.com search results.

Retrieval is decided by MYNTRA_DATA_SOURCE (see app/core/config.py):

1. "http" (default, Phase C): the browser-free HTTP path.  Myntra renders the
   full search results into the initial HTML inside a `window.__myx` JSON blob
   (`searchData.results.products`).  A plain `requests` GET (HTTP/1.1) fetches
   that and we parse the embedded products.  This avoids the Chromium HTTP/2
   handshake that Myntra intermittently resets (`ERR_HTTP2_PROTOCOL_ERROR`).
   No Playwright is invoked by this path and any HTTP failure returns honest
   empty [] (never a browser fallback).

2. "scraper" (legacy): HTTP path primary, then the original Playwright browser
   strategy (`li.product-base` structural cards) as a transparent fallback.

Normalisation, price parsing, deduplication and product-key logic are shared
by both paths (see normalise_myntra_product / _dedupe_by_product_key), and
every offer is enriched with the cross-marketplace canonical contract fields
(see app/scrapers/contract.py): product_id (payload productId, falling back to
the trailing numeric URL segment), original_price (MRP, when above the selling
price), currency=INR, captured_at and source_kind.

Failure contract:
  - On any error (markup change, Myntra blocking the request, browser or HTTP
    failure) return [] (honest empty for this source).
  - Never fabricate products, prices, or URLs.
  - Never raise — the pipeline already wraps calls defensively.
"""

import json
import logging
import re
from urllib.parse import quote_plus

import requests
from playwright.sync_api import sync_playwright

from app.core.config import get_settings
from app.scrapers.contract import normalize_offer
from app.utils.http_client import get_headers
from app.utils.text_utils import generate_product_key
from app.services.ranking_service import calculate_match_score

logger = logging.getLogger(__name__)

# Myntra lists each result as an <li> inside a results grid.  The stable
# card classes (used across Myntra's search result pages and documented in
# the public scraper ecosystem) are queried defensively below.
_PRODUCT_CARD_SELECTOR = "li.product-base"


def build_search_url(query: str) -> str:
    """Build the Myntra search URL for any query (path-based search)."""
    encoded_query = quote_plus(query)
    base = get_settings().myntra_base_url.rstrip("/")
    # Myntra uses path-based search results: https://www.myntra.com/<query>
    return f"{base}/{encoded_query}"


# Single JavaScript pass that pulls the raw, minimally-shaped fields out of
# every result card.  Keeping the browser-side extraction separate from the
# pure normaliser lets the latter be unit-tested offline with fixture data.
_EXTRACT_PRODUCTS_JS = """
() => {
    const results = [];
    const cards = document.querySelectorAll('li.product-base');
    for (const card of cards) {
        const out = { brand: '', name: '', price_text: '', url: '', image: '' };

        const brandEl = card.querySelector('.product-brand');
        if (brandEl) out.brand = (brandEl.textContent || '').trim();

        const nameEl = card.querySelector('.product-product');
        if (nameEl) out.name = (nameEl.textContent || '').trim();

        // Title fallback: the best non-empty text node inside the card.
        if (!out.name) {
            const name = card.querySelector('h4, p');
            if (name) out.name = (name.textContent || '').trim();
        }

        // Link: the product anchor points at /<slug>/<id>/buy
        const link = card.querySelector('a[href*="/buy"], a[href*="/buy?"]');
        if (!link) {
            const anyLink = card.querySelector('a[href]');
            if (anyLink) out.url = anyLink.getAttribute('href') || '';
        } else {
            out.url = link.getAttribute('href') || '';
        }

        // Price: prefer the discounted (sale) price, then the generic price.
        const discEl = card.querySelector('.product-discountedPrice');
        const priceEl = card.querySelector('.product-price');
        if (discEl && discEl.textContent) {
            out.price_text = (discEl.textContent || '').trim();
        } else if (priceEl) {
            out.price_text = (priceEl.textContent || '').trim();
        }

        // Image: Myntra renders the visible image in src, but older markup
        // uses data-src for lazy loading, so check both.
        const img = card.querySelector('img.img-responsive, img');
        if (img) {
            const src =
                img.getAttribute('src') ||
                img.getAttribute('data-src') ||
                '';
            out.image = src.trim();
        }

        results.push(out);
    }
    return results;
}
"""


# Displays can include a strike-through MRP / discount label after the real
# price, so we only keep the FIRST valid Indian-currency amount.
_PRICE_RE = re.compile(r"([\u20b9]?)\s*(\d+(?:,\d{2,3})*(?:\.\d+)?)")


def _parse_price(price_text):
    """
    Parse an Indian-currency price string ("₹49,999", "₹55,999", "1,919",
    "Rs. 45,000") into (value, display).  Returns (0, "Check price") when
    no valid positive amount can be extracted.
    """
    if not price_text:
        return 0, "Check price"

    match = _PRICE_RE.search(price_text)
    if not match:
        return 0, "Check price"

    sign, digits = match.group(1), match.group(2)
    cleaned = re.sub(r"[^\d.]", "", digits)
    try:
        value = float(cleaned) if cleaned else 0.0
    except ValueError:
        value = 0.0

    if value <= 0:
        return 0, "Check price"

    display = f"\u20b9{int(value):,}"
    return value, display


def _absolute_url(url):
    """
    Normalise a Myntra product URL to an absolute https URL.

    Myntra links are relative ("/<slug>/<id>/buy"); prefix the configured
    base host when they are.  Absolute URLs pass through unchanged.
    """
    if not url:
        return None
    u = str(url).strip()
    if not u:
        return None
    if u.startswith("http://") or u.startswith("https://"):
        return u
    base = get_settings().myntra_base_url.rstrip("/")
    return base + ("/" if not u.startswith("/") else "") + u


# Myntra product URLs end in /<productId>/buy (e.g. /shirts/brand/123456/buy),
# so the digits immediately before "/buy" (or at the path tail) are the
# source's own product identity.  Used only when the payload did not expose a
# productId; never fabricated from prose.
_PRODUCT_ID_RE = re.compile(r"(\d+)(?:/buy)?$")


def _product_id_from_url(url):
    """Extract the trailing numeric Myntra product id from *url*, or ''."""
    if not url:
        return ""
    path = str(url).split("?", 1)[0].strip().rstrip("/")
    match = _PRODUCT_ID_RE.search(path)
    return match.group(1) if match else ""


def normalise_myntra_product(raw, query, source_kind=""):
    """
    Convert one raw Myntra record into the shared DealCompare product dict.

    Raw fields: {brand, name, price_text, url, image}.
    Returns None (caller should skip) when the record cannot be safely
    turned into a valid offer — no title, no usable price, or no URL.
    """
    if not isinstance(raw, dict):
        return None

    brand = (raw.get("brand") or "").strip()
    name = (raw.get("name") or "").strip()

    title = " ".join(t for t in (brand, name) if t).strip()
    if not title or len(title.split()) < 3:
        return None

    price_value, price_display = _parse_price(raw.get("price_text") or "")
    if price_value <= 0:
        return None

    url = _absolute_url(raw.get("url"))
    if not url:
        return None

    product_key = generate_product_key(title)
    if not product_key:
        return None

    score = calculate_match_score(query, title)
    if score < get_settings().match_score_threshold:
        return None

    image = (raw.get("image") or "").strip()
    if image and not (image.startswith("http://") or image.startswith("https://")):
        image = _absolute_url(image)

    product_id = (raw.get("product_id") or _product_id_from_url(url)).strip()

    offer = {
        "title": title,
        "product_key": product_key,
        "platform": "Myntra",
        "price_value": price_value,
        "price_display": price_display,
        "url": url,
        "image": image or "",
        "product_id": product_id or None,
    }

    # MRP (compare price) — only when strictly above the selling price.
    mrp = raw.get("mrp")
    try:
        mrp = float(mrp) if mrp is not None else 0.0
    except (TypeError, ValueError):
        mrp = 0.0
    if mrp > price_value:
        offer["original_price"] = mrp
    offer["currency"] = "INR"

    return normalize_offer(offer, source_kind)


def _dedupe_by_product_key(products):
    """
    Collapse a list of normalised offers so there is at most one offer per
    product_key, keeping the cheapest price for a repeated product.  Myntra
    renders the same product in multiple near-identical cards within a single
    results page, so this must produce exactly one Myntra offer per card.
    """
    seen = {}
    for product in products:
        key = product.get("product_key")
        if not key:
            continue
        if key not in seen or product["price_value"] < seen[key]["price_value"]:
            seen[key] = product
    return list(seen.values())


# ---------------------------------------------------------------------------
# HTTP retrieval path (primary)
#
# Myntra embeds the full search results into the initial HTML inside a
# `window.__myx` JSON blob under `searchData.results.products`.  A plain HTTP
# GET avoids the Chromium HTTP/2 handshake that Myntra intermittently resets,
# so this path restores real results where the browser path returns nothing.
# ---------------------------------------------------------------------------

# Myntra preloads search results into window.__myx = {...};  the object is the
# sole statement in its <script> tag and closes immediately before </script>.
_MYX_MARKER = "window.__myx = "


def _extract_html_products(html: str, query: str) -> list:
    """
    Pull the raw product records out of a Myntra search HTML page.

    Parses the `window.__myx` JSON blob (`searchData.results.products`) and
    maps each entry into the shared raw Myntra shape the normaliser expects:

        {brand, name, price_text, url, image}

    Returns [] when the JSON is missing/unparseable or there are no products.
    Never fabricates data — only fields present in the source are mapped.
    """
    if not html:
        return []

    start = html.find(_MYX_MARKER)
    if start == -1:
        return []

    end = html.find("</script>", start)
    if end == -1:
        return []

    blob = html[start + len(_MYX_MARKER):end].strip()
    if blob.endswith(";"):
        blob = blob[:-1]

    try:
        data = json.loads(blob)
    except (ValueError, TypeError):
        return []

    if not isinstance(data, dict):
        return []

    products = (
        (data.get("searchData") or {}).get("results") or {}
    ).get("products")
    if not isinstance(products, list):
        return []

    raw = []
    for p in products:
        if not isinstance(p, dict):
            continue

        name = (p.get("productName") or p.get("product") or "").strip()
        brand = (p.get("brand") or "").strip()
        url = (p.get("landingPageUrl") or "").strip()

        # --- selling price with MRP fallback (kept real, never invented) ---
        price = p.get("price")
        try:
            price = float(price) if price is not None else 0.0
        except (TypeError, ValueError):
            price = 0.0
        mrp = p.get("mrp")
        try:
            mrp = float(mrp) if mrp is not None else 0.0
        except (TypeError, ValueError):
            mrp = 0.0
        if price <= 0 and mrp > 0:
            price = mrp
        price_text = f"\u20b9{int(price)}" if price > 0 else ""

        image = (p.get("searchImage") or "").strip()
        # Myntra serves these on an http URL in the payload; https is safe.
        if image.startswith("http://"):
            image = "https://" + image[len("http://"):]

        product_id = p.get("productId")
        if product_id is not None:
            product_id = str(product_id).strip()
        raw.append({
            "brand": brand,
            "name": name,
            "price_text": price_text,
            "url": url,
            "image": image,
            # extra fields for the shared contract: MRP (compare price) and the
            # source's own product identity.  Kept real — absent values stay
            # empty so a strict match is never seeded by a guessed value.
            "mrp": mrp if mrp > 0 else 0.0,
            "product_id": product_id or "",
        })

    return raw


def _fetch_myntra_http(query: str):
    """
    Fetch the Myntra search HTML over plain HTTP/1.1.

    Returns the decoded page text on a 200, otherwise None.  Never raises —
    network/protocol errors are converted to None so the caller can fall back
    to the Playwright path.  Uses the shared request headers (UA + language).
    """
    settings = get_settings()
    url = build_search_url(query)
    try:
        resp = requests.get(
            url,
            headers=get_headers(),
            timeout=getattr(settings, "http_timeout_seconds", 8.0),
        )
    except requests.exceptions.RequestException as e:
        logger.warning("Myntra HTTP request failed: %s", e)
        return None

    if resp.status_code != 200:
        logger.warning("Myntra HTTP returned status %s", resp.status_code)
        return None

    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def _normalise_html_products(raw_products: list, query: str) -> list:
    """Normalise raw HTTP-extracted records into DealCompare offers."""
    gathered = []
    for raw in raw_products:
        try:
            normalised = normalise_myntra_product(raw, query, source_kind="http")
        except Exception as e:
            logger.warning("Myntra HTTP normalise error: %s", e)
            continue
        if not normalised:
            continue
        gathered.append(normalised)
        if len(gathered) >= get_settings().max_results_per_platform:
            break
    return _dedupe_by_product_key(gathered)


def _search_myntra_http(query: str) -> list:
    """
    Run the Myntra HTTP retrieval path and normalise its products.

    Returns [] (honest empty) on any HTTP failure, non-200, missing/invalid
    embedded JSON, or when no usable offers survive normalisation — so the
    caller can transparently fall back to the Playwright scraper.
    """
    html = _fetch_myntra_http(query)
    if not html:
        return []

    raw_products = _extract_html_products(html, query)
    if not raw_products:
        return []

    results = _normalise_html_products(raw_products, query)
    logger.info("Myntra HTTP path: %d results", len(results))
    return results


def _search_myntra_scraper(query: str) -> list:
    """
    Run the existing Playwright browser scraper for *query*.

    Extracted to its own helper (preserved behaviour) so search_myntra() can
    try the HTTP path first and fall back here.
    """
    settings = get_settings()
    url = build_search_url(query)
    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.headless_browser)
            context = browser.new_context(
                user_agent=settings.user_agent,
                viewport={"width": 1280, "height": 2000},
                locale="en-IN",
            )
            page = context.new_page()

            logger.debug("Opening Myntra URL: %s", url)

            try:
                page.goto(
                    url,
                    timeout=settings.page_load_timeout_ms,
                    wait_until="domcontentloaded",
                )
            except Exception as e:
                logger.warning("Myntra page load failed: %s", e)
                browser.close()
                return []

            # Let the client-side search results render.
            page.wait_for_timeout(int(settings.selector_timeout_ms / 2))

            try:
                raw_products = page.evaluate(_EXTRACT_PRODUCTS_JS)
            except Exception as e:
                logger.warning("Myntra DOM extraction failed: %s", e)
                raw_products = []

            logger.debug("Myntra raw cards extracted: %d", len(raw_products))

            gathered = []

            for raw in raw_products:
                try:
                    normalised = normalise_myntra_product(raw, query, source_kind="scrape")
                except Exception as e:
                    logger.warning("Myntra normalise error: %s", e)
                    continue

                if not normalised:
                    continue

                gathered.append(normalised)

                if len(gathered) >= settings.max_results_per_platform:
                    break

            results = _dedupe_by_product_key(gathered)

            browser.close()

        logger.info("Myntra returned: %d results", len(results))
        return results

    except Exception as e:
        logger.error("Myntra scraping error: %s", e)
        return []


def _myntra_uses_legacy_fallback() -> bool:
    """True only when MYNTRA_DATA_SOURCE=scraper (legacy HTTP+Playwright)."""
    return getattr(get_settings(), "myntra_data_source", "http").strip().lower() == "scraper"


def search_myntra(query: str):
    """
    Search Myntra for products matching *query*.

    Retrieval dispatch is controlled by MYNTRA_DATA_SOURCE:
      - "http" (default, Phase C): the browser-free HTTP/__myx path only.
        No Playwright is ever invoked by the normal Myntra path, and a failed
        HTTP attempt returns [] — honest empty, never a browser fallback.
      - "scraper": preserves the legacy behaviour — HTTP path primary, then
        the existing Playwright browser scraper as a fallback.

    Returns:
        list[dict]: Normalised product dicts conforming to the shared
        DealCompare contract.  On any failure, returns [] (honest empty).
    """
    if not _myntra_uses_legacy_fallback():
        return _search_myntra_http(query)

    logger.info("Myntra data source: scraper (HTTP primary + Playwright fallback)")
    http_results = _search_myntra_http(query)
    if http_results:
        logger.info("Myntra used HTTP path: %d results", len(http_results))
        return http_results

    logger.warning(
        "Myntra HTTP path returned no usable results; falling back to Playwright"
    )
    return _search_myntra_scraper(query)
