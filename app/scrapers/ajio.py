"""
Ajio scraper — real product data from ajio.com search results.

IMPORTANT NOTE ON LIVE ACCESSIBILITY
------------------------------------
At the time of writing Ajio fronts its whole site (including the homepage and
every search route) behind an Akamai edge (errors.edgesuite.net) that returns
HTTP 403 "Access Denied" to automated browser sessions *and* plain HTTP
clients from datacenter/VPS IP ranges.  This block is unrelated to our code:
no user-agent, wait length, or headless toggle observed in probing changed
the outcome.

To stay faithful to the established failure contract (and to the project rule
that we *never fabricate* products, prices, or URLs), `search_ajio` attempts
the real browser pipeline and returns an honest empty list whenever that
block (or any network/browser/markup failure) occurs.  The pure normaliser,
URL builder, and DOM extractor are real, fully unit-tested code that will
start returning live offers the moment Ajio becomes reachable from the running
environment.

Extraction strategy (mirrors the Myntra/Flipkart pattern):
  1. Build the path-based search URL  https://www.ajio.com/search/<query>.
  2. Render the page with the shared Playwright strategy and read the product
     cards structurally inside a single page.evaluate call.
  3. Normalise each raw record via the pure `normalise_ajio_product`.

Failure contract:
  - On any error (blocked HTTP 403, markup change, browser failure) return []
    (honest empty for this source).
  - Never fabricate products, prices, or URLs.
  - Never raise — the pipeline already wraps calls defensively.
"""

import logging
import re
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from app.core.config import get_settings
from app.utils.text_utils import generate_product_key
from app.services.ranking_service import calculate_match_score

logger = logging.getLogger(__name__)

# Ajio's search route is path-based: https://www.ajio.com/search/<query>.
_BASE_URL = "https://www.ajio.com"


def build_search_url(query: str) -> str:
    """
    Build the Ajio search URL for any query (path-based, never a hardcoded
    product/category).  Encodes the query so it is URL-safe.
    """
    encoded_query = quote_plus(query)
    return f"{_BASE_URL}/search/{encoded_query}"


# Structured JS extraction of the raw fields out of every result card.
# Kept as a single island of browser-only logic so the pure normaliser below
# stays offline-unit-testable.  Selectors are defensive (with fallbacks) and
# the real card classes are supplied by the fixture/tests.
_EXTRACT_PRODUCTS_JS = """
() => {
    const results = [];
    const links = document.querySelectorAll('a[href*="/p/"]');
    const seen = new Set();
    for (const link of links) {
        const href = link.getAttribute('href') || '';
        if (!href || seen.has(href)) continue;
        seen.add(href);

        const out = { brand: '', name: '', price_text: '', url: href, image: '' };

        // Card container: climb from the product anchor, but stop at the
        // tightest ancestor that still represents a single product (exactly
        // one product link inside it).  This keeps each product scoped to its
        // own card instead of climbing up into a shared search grid, where
        // every card would read the first card's brand/name/price.
        let card = link;
        while (card.parentElement) {
            const parent = card.parentElement;
            if (parent.querySelectorAll('a[href*="/p/"]').length !== 1) break;
            card = parent;
        }

        // Brand + name: prefer headings inside the card, fall back to the
        // link's own text, then any short non-price text node.
        const brandEl = card.querySelector('.brand, .product-brand, [class*="brand"]');
        if (brandEl) out.brand = (brandEl.textContent || '').trim();
        const nameEl = card.querySelector('h3 a, h2 a, h3, h2, .name, .product-name, [class*="name"]');
        if (nameEl) out.name = (nameEl.textContent || '').trim();
        if (!out.name && link.textContent) out.name = (link.textContent || '').trim();
        if (!out.name) {
            const heads = card.querySelectorAll('h3, h2, h1');
            for (const h of heads) {
                const t = (h.textContent || '').trim();
                if (t) { out.name = t; break; }
            }
        }

        // Price: prefer a dedicated price element (class contains "price");
        // its text is validated downstream by _parse_price.  Only if no such
        // element exists do we scan text, and then we require an unmistakable
        // currency marker (rupee/Rs/INR) so an image dimension or product id
        // is never mistaken for a price.
        let priceNode = null;
        const priceEl = card.querySelector('[class*="price"], [class*="Price"]');
        const priceText = priceEl ? (priceEl.textContent || '').trim() : '';
        if (priceText && /[\d]/.test(priceText)) {
            priceNode = priceText;
        } else {
            const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, null, false);
            let n;
            while ((n = walker.nextNode())) {
                const t = (n.textContent || '').trim();
                if (/\u20b9|Rs\.|INR/i.test(t) && /[\d,]/.test(t)) { priceNode = t; break; }
            }
        }
        if (priceNode !== null) out.price_text = priceNode;

        // Image: first <img> inside the card.
        const img = card.querySelector('img[src], img[data-src]');
        if (img) out.image = img.getAttribute('src') || img.getAttribute('data-src') || '';

        results.push(out);
    }
    return results;
}
"""


# Displays can include a strike-through MRP / discount label after the real
# (discounted) price, so we only keep the FIRST valid Indian-currency amount.
_PRICE_RE = re.compile(r"([\u20b9]?)\s*(\d+(?:,\d{2,3})*(?:\.\d+)?)")


def _parse_price(price_text):
    """
    Parse an Indian-currency price string ("\u20b91,799", "Rs. 2,999",
    "1,199") into (value, display).  Returns (0, "Check price") when no
    valid positive amount can be extracted.
    """
    if not price_text:
        return 0, "Check price"

    match = _PRICE_RE.search(price_text)
    if not match:
        return 0, "Check price"

    _, digits = match.group(1), match.group(2)
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
    Normalise an Ajio product URL to an absolute https URL.

    Ajio links are relative ("/<slug>/<id>"); prefix the configured base host
    when they are.  Absolute URLs pass through unchanged.
    """
    if not url:
        return None
    u = str(url).strip()
    if not u:
        return None
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return _BASE_URL + ("/" if not u.startswith("/") else "") + u


def normalise_ajio_product(raw, query):
    """
    Convert one raw Ajio record into the shared DealCompare product dict.

    Raw fields: {brand, name, price_text, url, image}.
    Returns None (caller should skip) when the record cannot be safely turned
    into a valid offer — no title, no usable price, or no URL.
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

    return {
        "title": title,
        "product_key": product_key,
        "platform": "Ajio",
        "price_value": price_value,
        "price_display": price_display,
        "url": url,
        "image": image or "",
    }


def _dedupe_by_product_key(products):
    """
    Collapse a list of normalised offers so there is at most one offer per
    product_key, keeping the cheapest price for a repeated product.
    """
    seen = {}
    for product in products:
        key = product.get("product_key")
        if not key:
            continue
        if key not in seen or product["price_value"] < seen[key]["price_value"]:
            seen[key] = product
    return list(seen.values())


def search_ajio(query: str):
    """
    Search Ajio for products matching *query*.

    Returns:
        list[dict]: Normalised product dicts conforming to the shared
        DealCompare contract.  On any failure (including Ajio's anti-bot
        HTTP 403 block) returns [] — honest empty, never fabricated data.
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

            logger.debug("Opening Ajio URL: %s", url)

            try:
                page.goto(
                    url,
                    timeout=settings.page_load_timeout_ms,
                    wait_until="domcontentloaded",
                )
            except Exception as e:
                logger.warning("Ajio page load failed: %s", e)
                browser.close()
                return []

            # Let any client-side search results render.
            page.wait_for_timeout(int(settings.selector_timeout_ms / 2))

            try:
                raw_products = page.evaluate(_EXTRACT_PRODUCTS_JS)
            except Exception as e:
                logger.warning("Ajio DOM extraction failed: %s", e)
                raw_products = []

            logger.debug("Ajio raw cards extracted: %d", len(raw_products))

            gathered = []
            for raw in raw_products:
                try:
                    normalised = normalise_ajio_product(raw, query)
                except Exception as e:
                    logger.warning("Ajio normalise error: %s", e)
                    continue

                if not normalised:
                    continue

                gathered.append(normalised)

                if len(gathered) >= settings.max_results_per_platform:
                    break

            results = _dedupe_by_product_key(gathered)

            browser.close()

        logger.info("Ajio returned: %d results", len(results))
        return results

    except Exception as e:
        logger.error("Ajio scraping error: %s", e)
        return []
