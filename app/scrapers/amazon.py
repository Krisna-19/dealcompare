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

# A valid amount is only bare digits (optionally a decimal fraction).  Prose
# like "No Cost EMI" or "Free Delivery" fails this check and must never become
# a product price.
_AMOUNT_RE = re.compile(r"^\d+(?:\.\d+)?$")


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


def _all_text(item, selector):
    """Yield the trimmed inner_text of every element matching *selector*."""
    try:
        elements = item.query_selector_all(selector)
    except Exception:
        return
    for element in elements:
        try:
            text = element.inner_text().strip()
        except Exception:
            continue
        if text:
            yield text


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


def _absolute_url(href):
    """
    Join a (possibly relative) Amazon href onto the configured base host.

    Search-result links are relative ("/dp/<ASIN>...", "/sspa/click?...");
    prefix the configured amazon_base_url instead of a hardcoded hostname so
    every product URL is valid for the configured storefront.
    """
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    base = get_settings().amazon_base_url.rstrip("/")
    return base + ("/" if not href.startswith("/") else "") + href


def _parse_offscreen_price(text):
    """
    Parse one a-offscreen snippet into (value, display) or None.

    Only a bare currency amount ("₹59,900", "Rs. 59,900") is a price.  Amazon
    stores other screen-reader copy in the same spans — "No Cost EMI", "Free
    Delivery", "EMI ₹4,999/month" — and that prose must never be minted into
    a price.  Returns None when no valid positive amount can be extracted so
    the caller keeps the honest "Check price" contract.
    """
    if not text:
        return None
    stripped = text.strip()
    without_currency = re.sub(
        r"^(?:[₹\u20b9]\s*|Rs\.?\s*|INR\s*)", "", stripped, flags=re.IGNORECASE
    ).strip()
    collapsed = re.sub(r"[\s,]", "", without_currency)
    if not collapsed or not _AMOUNT_RE.fullmatch(collapsed):
        return None
    try:
        value = float(collapsed)
    except ValueError:
        return None
    if value <= 0:
        return None
    # Display keeps the historical shape (deduplicated digits, no commas).
    return value, f"₹{collapsed}"


def extract_product_details(item):
    """
    Extract raw product fields from one search-result element.

    Returns a dict with title/product_url/price_value/price_display/image,
    or None when the item has no usable title and link (e.g. markup change).
    A missing or unparseable price keeps the historical contract (0 /
    "Check price"); unrelated copy like "No Cost EMI" or "Free Delivery" is
    never treated as a price.
    """
    title = _first_text(item, TITLE_SELECTORS)
    href = _first_attribute(item, LINK_SELECTORS, "href")

    if not title or not href:
        return None

    product_url = _absolute_url(href)

    price_value = 0
    price_display = "Check price"
    for price_text in _all_text(item, PRICE_SELECTOR):
        parsed = _parse_offscreen_price(price_text)
        if parsed is not None:
            price_value, price_display = parsed
            break

    image = _first_attribute(item, [IMAGE_SELECTOR], "src") or ""

    return {
        "title": title,
        "product_url": product_url,
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