"""
Pure affiliate URL transform for the /search response boundary.

Maps an offer's real product URL to its affiliate URL by appending the
platform's configured affiliate tag to the *actual* product destination, so a
"View Deal" button still opens the same product page while becoming trackable.

The transform is intentionally additive and side-effect free:
  - It never changes product grouping, identity, dedup, price, or offer shape
    (those are computed on the ORIGINAL urls before this runs).
  - It never touches prices, titles, or platform fields.
  - A platform with no configured tag returns the original URL unchanged.
"""

from urllib.parse import urlparse

from app.core.config import get_settings


def _append_tag(url: str, tag: str) -> str:
    """
    Append an affiliate *tag* query parameter to a URL, preserving any existing
    query string (use '&' vs '?' correctly).  An empty tag returns the URL
    unchanged.
    """
    if not tag:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}tag={tag}"


def _platform_tag(platform: str) -> str:
    """The configured affiliate tag for a platform ('' when unset)."""
    settings = get_settings()
    key = f"{str(platform or '').lower()}_affiliate_tag"
    value = getattr(settings, key, None)
    return value or ""


def apply_affiliate_url(product_url, platform):
    """
    Return *product_url* with the platform's affiliate tag appended.
    If the platform has no configured tag, or the URL is unusable, the URL is
    returned unchanged (never None, never fabricated).
    """
    if not product_url or not isinstance(product_url, str):
        return product_url or ""
    u = product_url.strip()
    if not u:
        return u

    tag = _platform_tag(platform)
    if not tag:
        return u
    return _append_tag(u, tag)


def enrich_offer(offer, platform=None):
    """
    Return a *copy* of a single offer dict whose 'url' has the affiliate tag
    applied.  All other fields are preserved by reference.  The original dict
    (and the original 'url' value) are never mutated.
    """
    if not isinstance(offer, dict):
        return offer
    source_platform = platform if platform is not None else offer.get("platform")
    enriched = dict(offer)
    enriched["url"] = apply_affiliate_url(offer.get("url"), source_platform)
    return enriched


def enrich_offers_in_card(card):
    """
    Return a *copy* of an aggregated product card with each offer's url tagged.
    The card's own title / best_price / best_platform / best_url are left
    unchanged (best_price was computed on original urls upstream).
    """
    if not isinstance(card, dict):
        return card
    enriched = dict(card)
    offers = [enrich_offer(o) for o in (card.get("offers") or [])]
    enriched["offers"] = offers
    return enriched


def enrich_results(results):
    """
    Apply the affiliate transform to every offer inside a list of aggregated
    product cards.  Pure: returns a new list and never mutates the input.
    """
    if not isinstance(results, list):
        return results
    return [enrich_offers_in_card(card) for card in results]
