import urllib.parse

AMAZON_TAG = "dealcompare19-21"  # your Store ID

def build_amazon_search_link(query: str) -> str:
    """
    Builds a compliant Amazon affiliate search URL
    (No scraping, no API)
    """
    encoded_query = urllib.parse.quote_plus(query)
    return (
        f"https://www.amazon.in/s?"
        f"k={encoded_query}"
        f"&tag={AMAZON_TAG}"
    )
