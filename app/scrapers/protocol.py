"""
Source-adapter protocol for DealCompare e-commerce scrapers.

Every source module must expose a callable with this signature:

    def search_<source>(query: str) -> list[dict]:

The callable must return a list of product dictionaries conforming to the
shared contract:

    {
        "title":        str,    # product title as shown on the source
        "product_key":  str,    # grouping key (brand-model-storage)
        "platform":     str,    # display name, e.g. "Amazon", "Flipkart"
        "price_value":  float,  # numeric price (>0); 0 = placeholder
        "price_display": str,   # formatted price, e.g. "₹79,999"
        "url":          str,    # full product page URL
        "image":        str,    # product image URL (optional, may be "")
    }

Failure contract:
    - On any error, return [] (honest empty for that source).
    - Never fabricate products, prices, or platform data.
    - Never raise exceptions — the pipeline wraps calls defensively.
"""
