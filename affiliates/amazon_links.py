import urllib.parse

from app.core.config import get_settings


def _append_tag(url: str, tag: str) -> str:
    """
    Append an affiliate *tag* query parameter to a URL, preserving any existing
    query string (use '&' vs '?' correctly).  An empty tag returns the URL
    unchanged, so platforms without a configured tag stay raw.
    """
    if not tag:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}tag={tag}"


def build_amazon_search_link(query: str) -> str:
    """
    Builds a compliant Amazon affiliate search URL
    (No scraping, no API)
    """
    settings = get_settings()
    encoded_query = urllib.parse.quote_plus(query)
    base = settings.affiliate_base_url.rstrip("/")
    return (
        f"{base}/s?"
        f"k={encoded_query}"
        f"&tag={settings.amazon_affiliate_tag}"
    )


def build_flipkart_search_link(query: str) -> str:
    """
    Builds a Flipkart search URL with the optional affiliate tag appended.
    Uses the configured base URL; returns a plain (untagged) URL when no
    affiliate tag is configured.
    """
    settings = get_settings()
    encoded_query = urllib.parse.quote_plus(query)
    base = settings.flipkart_base_url.rstrip("/")
    url = f"{base}/search?q={encoded_query}"
    return _append_tag(url, settings.flipkart_affiliate_tag)


def build_myntra_search_link(query: str) -> str:
    """
    Builds a Myntra search URL (path-based) with the optional affiliate tag
    appended.  Returns a plain (untagged) URL when no tag is configured.
    """
    settings = get_settings()
    encoded_query = urllib.parse.quote_plus(query)
    base = settings.myntra_base_url.rstrip("/")
    url = f"{base}/{encoded_query}"
    return _append_tag(url, settings.myntra_affiliate_tag)


def build_ajio_search_link(query: str) -> str:
    """
    Builds an Ajio search URL (path-based: /search/<query>) with the optional
    affiliate tag appended.  Returns a plain (untagged) URL when no tag is
    configured.
    """
    settings = get_settings()
    encoded_query = urllib.parse.quote_plus(query)
    base = settings.ajio_base_url.rstrip("/")
    url = f"{base}/search/{encoded_query}"
    return _append_tag(url, settings.ajio_affiliate_tag)


# Platform name -> (search-link builder, affiliate tag) for the offer-URL
# transform.  The transform appends the tag to the *actual* product URL so the
# "View Deal" destination is unchanged; an empty tag leaves the URL as-is.
_BUILDERS = {
    "amazon": build_amazon_search_link,
    "flipkart": build_flipkart_search_link,
    "myntra": build_myntra_search_link,
    "ajio": build_ajio_search_link,
}
