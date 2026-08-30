import logging
import re
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from app.core.config import get_settings
from app.utils.text_utils import generate_product_key
from app.services.ranking_service import calculate_match_score

logger = logging.getLogger(__name__)


def build_search_url(query: str) -> str:
    """Build the Amazon search URL for any query (no category/category-facet hardcoding)."""
    encoded_query = quote_plus(query)
    base = get_settings().amazon_base_url.rstrip("/")
    return f"{base}/s?k={encoded_query}"


# Selector fallback chains, ordered current-layout-first. Amazon changes its
# result-card markup periodically; every field is extracted defensively.
TITLE_SELECTORS = [
    "a.a-link-normal.s-line-clamp-2",        # current layout: anchor wraps h2
    "[data-cy='title-recipe'] a h2 span",    # structural variant
    "h2 a span",                             # legacy layout: h2 wraps anchor
    "h2 span",                               # last resort (may be brand-only)
]

LINK_SELECTORS = [
    "a.a-link-normal.s-line-clamp-2",        # same anchor as the title
    "a[href*='/dp/']",
    "h2 a",                                  # legacy layout
]

PRICE_SELECTOR = "span.a-offscreen"
IMAGE_SELECTOR = "img.s-image"


def _first_text(item, selectors):
    """Return the first non-empty inner_text among selectors, else None."""
    for selector in selectors:
        try:
            element = item.query_selector(selector)
        except Exception:
            continue
        if element:
            text = element.inner_text().strip()
            if text:
                return text
    return None


def _first_attribute(item, selectors, attribute):
    """Return the first non-empty attribute value among selectors, else None."""
    for selector in selectors:
        try:
            element = item.query_selector(selector)
        except Exception:
            continue
        if element:
            value = element.get_attribute(attribute)
            if value:
                return value
    return None


def extract_product_details(item):
    """
    Extract raw product fields from one search-result element.

    Returns a dict with title/product_url/price_value/price_display/image,
    or None when the item has no usable title and link (e.g. markup change).
    A missing price keeps the historical contract (0 / "Check price").
    """
    title = _first_text(item, TITLE_SELECTORS)
    href = _first_attribute(item, LINK_SELECTORS, "href")

    if not title or not href:
        return None

    price_value = 0
    price_display = "Check price"

    price_text = _first_text(item, [PRICE_SELECTOR])
    if price_text:
        # Strip currency symbols, separators and whitespace defensively.
        cleaned = re.sub(r"[^\d.]", "", price_text)
        try:
            parsed = float(cleaned) if cleaned else 0
        except ValueError:
            parsed = 0
        if parsed > 0:
            price_value = parsed
            price_display = f"₹{cleaned}"

    image = _first_attribute(item, [IMAGE_SELECTOR], "src") or ""

    return {
        "title": title,
        "product_url": "https://www.amazon.in" + href,
        "price_value": price_value,
        "price_display": price_display,
        "image": image,
    }


def search_amazon(query: str):

    settings = get_settings()
    url = build_search_url(query)

    results = []

    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(headless=settings.headless_browser)

            context = browser.new_context(
                user_agent=settings.user_agent
            )

            page = context.new_page()

            logger.debug("Opening Amazon URL: %s", url)

            page.goto(url, timeout=settings.page_load_timeout_ms)

            page.wait_for_selector(
                'div[data-component-type="s-search-result"]',
                timeout=settings.selector_timeout_ms
            )

            logger.debug("Page loaded")

            products = page.query_selector_all(
                'div[data-component-type="s-search-result"]'
            )

            logger.debug("Valid product containers: %d", len(products))

            for product in products:

                try:

                    details = extract_product_details(product)

                    if not details:
                        continue

                    title = details["title"]

                    # Reject short / invalid titles
                    if len(title.split()) < 3:
                        continue

                    score = calculate_match_score(query, title)

                    logger.debug("TITLE: %s", title)
                    logger.debug("SCORE: %s", score)

                    if score < settings.match_score_threshold:
                        continue

                    product_key = generate_product_key(title)

                    if not product_key:
                        continue

                    results.append({
                        "title": title,
                        "product_key": product_key,
                        "platform": "Amazon",
                        "price_value": details["price_value"],
                        "price_display": details["price_display"],
                        "url": details["product_url"],
                        "image": details["image"]
                    })

                except Exception as e:
                    logger.warning("Loop error during extraction: %s", e)
                    continue

                # Limit results
                if len(results) >= settings.max_results_per_platform:
                    break

            browser.close()

        logger.info("Amazon returned: %d results", len(results))

        return results

    except Exception as e:
        logger.error("Amazon scraping error: %s", e)
        return []