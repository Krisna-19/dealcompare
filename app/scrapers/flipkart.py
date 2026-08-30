"""
Flipkart scraper — real product data from flipkart.com search results.

Extraction strategy (most durable first):
  1. __NEXT_DATA__ JSON — embedded by Next.js on server render, survives
     CSS class rotations (~2-week cycle on Flipkart).
  2. DOM fallback — structural selectors targeting visible product cards
     when __NEXT_DATA__ is unavailable (e.g. client-side navigation).

Failure contract:
  - On any error, return [] (honest empty).  Never fabricate products.
"""

import json
import logging
import re
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from app.core.config import get_settings
from app.utils.text_utils import generate_product_key
from app.services.ranking_service import calculate_match_score

logger = logging.getLogger(__name__)


def build_search_url(query: str) -> str:
    """Build the Flipkart search URL for any query."""
    encoded_query = quote_plus(query)
    base = get_settings().flipkart_base_url.rstrip("/")
    return f"{base}/search?q={encoded_query}"


# ---------------------------------------------------------------------------
# Strategy 1: __NEXT_DATA__ JSON extraction
# ---------------------------------------------------------------------------

def _extract_from_next_data(page):
    """
    Pull structured product data from the __NEXT_DATA__ script tag
    embedded by Next.js on server-side render.

    Returns a list of raw product dicts, or [] if unavailable.
    """
    try:
        raw = page.evaluate(
            '() => { const el = document.getElementById("__NEXT_DATA__"); '
            'return el ? el.textContent : null; }'
        )
    except Exception:
        return []

    if not raw:
        return []

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []

    # Navigate the Next.js data tree to find product listings.
    # The structure is: props.pageProps.initialData.data.cards
    # Each card may contain widget data with product arrays.
    products = []
    try:
        page_props = data.get("props", {}).get("pageProps", {})
        initial_data = page_props.get("initialData", {})
        cards = initial_data.get("data", {}).get("cards", [])

        for card in cards:
            # Cards can have different shapes; dig for product lists
            widget = card.get("card", {}).get("widget", {})
            widget_data = widget.get("data", {})
            product_list = widget_data.get("products", [])

            if not product_list:
                # Alternate path: card itself may contain product info
                product_list = widget_data.get("result", {}).get("data", [])

            for p in product_list:
                if not isinstance(p, dict):
                    continue
                products.append(p)
    except (AttributeError, TypeError):
        return []

    return products


def _normalise_next_data_product(raw):
    """
    Convert a __NEXT_DATA__ product entry into the DealCompare product dict.

    Flipkart's JSON schema varies; we defensively handle multiple known
    field-name variants for title, price, URL, and image.
    """
    # --- title ---
    title = (
        raw.get("productBrand")
        or raw.get("title")
        or raw.get("productBaseInfoV1", {}).get("productAttributes", {}).get("title")
        or ""
    )
    if not title:
        return None

    # --- price ---
    price_value = 0
    price_display = "Check price"

    # Try multiple price paths
    pricing = raw.get("pricing", {})
    if isinstance(pricing, dict):
        price_value = pricing.get("sellingPrice", 0) or 0
        if not price_value:
            price_value = pricing.get("mrp", 0) or 0

    if not price_value:
        # Alternate: productBaseInfoV1 path
        base_info = raw.get("productBaseInfoV1", {})
        if isinstance(base_info, dict):
            attrs = base_info.get("productAttributes", {})
            if isinstance(attrs, dict):
                mrp = attrs.get("mrp", {})
                if isinstance(mrp, dict):
                    price_value = mrp.get("value", 0) or 0
                if not price_value:
                    sp = attrs.get("sellingPrice", {})
                    if isinstance(sp, dict):
                        price_value = sp.get("value", 0) or 0

    if not price_value:
        # Last resort: numeric field on root
        price_value = raw.get("price", 0) or raw.get("finalPrice", 0) or 0

    if isinstance(price_value, str):
        cleaned = re.sub(r"[^\d.]", "", price_value)
        try:
            price_value = float(cleaned) if cleaned else 0
        except ValueError:
            price_value = 0

    if price_value and price_value > 0:
        price_display = f"\u20b9{int(price_value):,}"
    else:
        price_value = 0
        price_display = "Check price"

    # --- url ---
    url = raw.get("productUrl", "") or ""
    if not url:
        pid = raw.get("productId", "") or raw.get("id", "")
        if pid:
            url = f"https://www.flipkart.com/p/{pid}"

    # Ensure absolute URL
    if url and not url.startswith("http"):
        url = f"https://www.flipkart.com{url}"

    if not url:
        return None

    # --- image ---
    image = ""
    image_data = raw.get("image", {})
    if isinstance(image_data, dict):
        image = image_data.get("url", "") or image_data.get("thumbnailUrl", "") or ""
    if not image:
        image_list = raw.get("images", [])
        if isinstance(image_list, list) and image_list:
            first = image_list[0]
            if isinstance(first, dict):
                image = first.get("url", "") or first.get("thumbnailUrl", "") or ""
            elif isinstance(first, str):
                image = first

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
    }


# ---------------------------------------------------------------------------
# Strategy 2: DOM / structural extraction fallback
# ---------------------------------------------------------------------------

# Flipkart rotates CSS classes every ~2 weeks.  Instead of relying on
# specific class names, we use a single JavaScript evaluation that
# extracts data structurally:
#   - [data-id] is a stable attribute on product cards
#   - <a> tags with /p/ in href are always product links
#   - <img> tags inside the card are always product images
#   - Text matching the rupee symbol is always the price
#   - The longest meaningful text node is typically the title

_EXTRACT_PRODUCTS_JS = """
() => {
    const results = [];
    const cards = document.querySelectorAll('[data-id]');

    for (const card of cards) {
        // --- URL: first <a> with /p/ in href ---
        const link = card.querySelector('a[href*="/p/"]');
        if (!link) continue;
        const href = link.getAttribute('href') || '';
        if (!href) continue;

        // --- Title: <img> alt text is the most reliable title source ---
        let title = '';
        const img = card.querySelector('img[alt]');
        if (img) {
            title = (img.getAttribute('alt') || '').trim();
        }
        // Fallback: longest text node that isn't a price
        if (!title) {
            const allText = [];
            const walker = document.createTreeWalker(
                card, NodeFilter.SHOW_TEXT, null, false
            );
            let node;
            while ((node = walker.nextNode())) {
                const t = node.textContent.trim();
                if (t && !t.match(/^[\\u20b9\\d,\\s]+$/) && t.length > 3) {
                    allText.push(t);
                }
            }
            if (allText.length) {
                title = allText.sort((a, b) => b.length - a.length)[0];
            }
        }
        if (!title || title.length < 3) continue;

        // --- Image ---
        let image = '';
        const imgEl = card.querySelector('img[src]');
        if (imgEl) {
            image = imgEl.getAttribute('src') || '';
        }

        // --- Price: find text matching ₹NNN pattern ---
        let price_value = 0;
        let price_display = 'Check price';
        const priceWalker = document.createTreeWalker(
            card, NodeFilter.SHOW_TEXT, null, false
        );
        let pNode;
        while ((pNode = priceWalker.nextNode())) {
            const txt = pNode.textContent.trim();
            const m = txt.match(/[\\u20b9](\\d[\\d,]*\\d)/);
            if (m) {
                const num = parseFloat(m[1].replace(/,/g, ''));
                if (num > 0) {
                    price_value = num;
                    price_display = '\\u20b9' + m[1];
                    break;
                }
            }
        }

        results.push({
            title: title,
            price_value: price_value,
            price_display: price_display,
            url: href,
            image: image,
        });
    }
    return results;
}
"""


def _extract_from_dom(page):
    """
    Fallback: extract product data using structural JS that doesn't
    depend on CSS class names (which Flipkart rotates every ~2 weeks).

    Stable anchors: [data-id], <a href="/p/...">, <img alt="...">
    Returns a list of raw dicts (un-normalised).
    """
    try:
        return page.evaluate(_EXTRACT_PRODUCTS_JS)
    except Exception as e:
        logger.debug("Flipkart DOM extraction failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_flipkart(query: str):
    """
    Search Flipkart for products matching *query*.

    Returns:
        list[dict]: Normalised product dicts conforming to the shared
        DealCompare contract.  On failure, returns [].
    """
    settings = get_settings()
    url = build_search_url(query)
    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.headless_browser)
            context = browser.new_context(
                user_agent=settings.user_agent,
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            logger.debug("Opening Flipkart URL: %s", url)

            try:
                page.goto(url, timeout=settings.page_load_timeout_ms)
            except Exception as e:
                logger.warning("Flipkart page load failed: %s", e)
                browser.close()
                return []

            # Close the login popup if it appears (common on Flipkart)
            try:
                close_btn = page.query_selector("button._2KpZ6l._2doB4z")
                if close_btn:
                    close_btn.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass

            # --- Strategy 1: __NEXT_DATA__ JSON ---
            raw_products = _extract_from_next_data(page)

            if raw_products:
                logger.debug(
                    "Flipkart __NEXT_DATA__: extracted %d raw products",
                    len(raw_products),
                )
                for raw in raw_products:
                    normalised = _normalise_next_data_product(raw)
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
            else:
                # --- Strategy 2: DOM fallback ---
                logger.debug("Flipkart __NEXT_DATA__ unavailable, trying DOM")
                dom_products = _extract_from_dom(page)
                logger.debug("Flipkart DOM: extracted %d raw products", len(dom_products))

                for raw in dom_products:
                    title = raw["title"]
                    if len(title.split()) < 2:
                        continue

                    product_key = generate_product_key(title)
                    if not product_key:
                        continue

                    score = calculate_match_score(query, title)
                    if score < settings.match_score_threshold:
                        continue

                    results.append({
                        "title": title,
                        "product_key": product_key,
                        "platform": "Flipkart",
                        "price_value": raw["price_value"],
                        "price_display": raw["price_display"],
                        "url": raw["url"],
                        "image": raw["image"],
                    })

                    if len(results) >= settings.max_results_per_platform:
                        break

            browser.close()

        logger.info("Flipkart returned: %d results", len(results))
        return results

    except Exception as e:
        logger.error("Flipkart scraping error: %s", e)
        return []
