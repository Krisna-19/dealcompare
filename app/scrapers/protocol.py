"""
Source-adapter protocol for DealCompare e-commerce scrapers.

Every source module must expose a callable with this signature:

    def search_<source>(query: str) -> list[dict]:

The callable must return a list of product dictionaries conforming to the
shared base contract:

    {
        "title":        str,    # product title as shown on the source
        "product_key":  str,    # grouping key (brand-model-storage)
        "platform":     str,    # display name, e.g. "Amazon", "Flipkart"
        "price_value":  float,  # numeric price (>0); 0 = placeholder
        "price_display": str,   # formatted price, e.g. "₹79,999"
        "url":          str,    # full product page URL
        "image":        str,    # product image URL (optional, may be "")
    }

SOURCE-SPECIFIC / CROSS-MARKETPLACE FIELDS (Phase G)
----------------------------------------------------
Every connector also annotates its offers with the canonical comparison set
via app/scrapers/contract.normalize_offer() so offers from different
marketplaces can be compared honestly:

    marketplace, marketplace_product_id, price, original_price, currency,
    availability, product_url, image_url, product_key, captured_at,
    source_kind

These are ADDITIVE: the aggregator, catalog and frontend only read the base
contract, pydantic response models strip the extras at the HTTP boundary, and
missing values are left empty/None so a match is never seeded by a guessed
value.  Where a source naturally has more identity it keeps it (e.g.
product_id = Flipkart PID / Myntra product id / Amazon ASIN).

Failure contract:
    - On any error, return [] (honest empty for that source).
    - Never fabricate products, prices, or platform data.
    - Never raise exceptions — the pipeline wraps calls defensively.

DATA-SOURCE SELECTION
-----------------------
Which retrieval path a marketplace uses is configured via the
`<key>_data_source` settings (amazon/flipkart/myntra/ajio; see
app/core/config.py) and read live by the connector registry, so enabling an
official API or deferring a blocked marketplace never requires edits here.
"""