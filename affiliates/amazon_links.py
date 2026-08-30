import urllib.parse

from app.core.config import get_settings


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
