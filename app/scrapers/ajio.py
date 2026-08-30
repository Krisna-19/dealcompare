"""
Ajio scraper - NOT IMPLEMENTED.

TODO: Implement a real Ajio search scraper (fetch or browser-automation
based) and map its output to the shared product dict shape:

    {
        "title": str,
        "product_key": str,
        "platform": "Ajio",
        "price_value": float,
        "price_display": str,
        "url": str,
        "image": str (optional),
    }

Until then this module deliberately returns no results instead of
fabricating placeholder products or prices.
"""


def search_ajio(query: str):
    """
    Search Ajio for products matching `query`.

    Returns:
        list: Always empty until a real scraper is implemented.
    """
    return []
