"""
Myntra scraper — real product data from myntra.com search results.

Myntra renders its search results with client-side JavaScript: a plain HTTP
response only returns the application shell (the product cards are injected
by the browser).  To stay consistent with the existing Amazon/Flipkart
adapters we therefore read the rendered DOM with the project's shared
Playwright browser strategy.

Extraction strategy:
  1. Navigate the browser to Myntra's path-based search URL.
  2. Read the product cards (`li.product-base`) structurally inside a single
     page.evaluate call — Myntra's card markup is stable and class-based
     (`.product-brand`, `.product-product`, `.product-price`, ...
     `.product-discountedPrice`), but we defensively fall back when a field
     is missing.
  3. Normalise each raw record into the shared DealCompare product dict.

Failure contract:
  - On any error (markup change, Myntra blocking the request, browser
    failure) return [] (honest empty for this source).
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


def normalise_myntra_product(raw, query):
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

    return {
        "title": title,
        "product_key": product_key,
        "platform": "Myntra",
        "price_value": price_value,
        "price_display": price_display,
        "url": url,
        "image": image or "",
    }


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


def search_myntra(query: str):
    """
    Search Myntra for products matching *query*.

    Returns:
        list[dict]: Normalised product dicts conforming to the shared
        DealCompare contract.  On any failure, returns [].
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
                    normalised = normalise_myntra_product(raw, query)
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
