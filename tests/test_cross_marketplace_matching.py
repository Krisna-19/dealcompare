"""
Cross-marketplace matching regression tests (Phase H).

The buying-the-known-object cases: the same physical SKU found on Amazon
(Creators API offers / ASIN), Flipkart (Affiliate API / productId), Myntra
(HTTP / product id) and Ajio must land in ONE comparison card, while genuine
variants (different storage / different model / genuinely different items)
must stay separate.

Identity priority exercised here (mirrors app/services/matching.py, which
reuses the aggregator's exact primitives):

    1. marketplace product identity (Flipkart productId / Amazon ASIN)
    2. brand + model + variant attributes (storage/RAM/colour/...)
    3. exact fallback product_key for attribute-less titles

Regression guard: similar titles ALONE never merge — an attribute-less title
pair merges only on an EXACT shared fallback key.

These tests never hit the network; they feed scraper/API-shaped offer dicts
through the real aggregator and matching functions.
"""
from app.aggregator.aggregator import aggregate_products
from app.services.matching import (
    compute_sku,
    compute_strong,
    match_offer,
    serialize_sku,
    serialize_strong,
)


def _offer(platform, title, price, url, product_id=None, product_key=None):
    offer = {
        "title": title,
        "product_key": product_key or f"{platform.lower()}-{price}",
        "platform": platform,
        "price_value": price,
        "price_display": f"\u20b9{int(price):,}",
        "url": url,
        "image": "",
    }
    if product_id:
        offer["product_id"] = product_id
    return offer


AMAZON_S24 = _offer(
    "Amazon",
    "Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
    59999.0,
    "https://www.amazon.in/dp/B0ONYX128",
    product_id="B0ONYX128",
    product_key="samsung-s24-128gb-amazon",
)
FLIPKART_S24 = _offer(
    "Flipkart",
    "Samsung Galaxy S24 5G Snapdragon 8 Gen 3 (Onyx Black, 128 GB)",
    54999.0,
    "https://www.flipkart.com/samsung-galaxy-s24/p/itm?pid=MOBONYX1",
    product_id="MOBONYX1",
    product_key="samsung-s24-128gb-flipkart",
)
MYNTRA_S24 = _offer(
    "Myntra",
    "Samsung Galaxy S24 5G (Onyx Black, 128 GB)",
    55999.0,
    "https://www.myntra.com/mobiles/samsung/ONYXMN/buy",
    product_id="ONYXMN",
    product_key="samsung-s24-128gb-myntra",
)
AJIO_S24 = _offer(
    "Ajio",
    "Samsung Galaxy S24 5G Mobile (Onyx Black, 128 GB)",
    56999.0,
    "https://www.ajio.com/samsung-galaxy-s24-5g/p/440001006",
    product_key="samsung-s24-128gb-ajio",
)


def test_same_s24_merges_across_all_four_marketplaces():
    results = aggregate_products([AMAZON_S24, FLIPKART_S24, MYNTRA_S24, AJIO_S24])

    assert len(results) == 1, "same SKU across 4 marketplaces must be ONE card"
    (group,) = results
    assert {o["platform"] for o in group["offers"]} == {
        "Amazon", "Flipkart", "Myntra", "Ajio",
    }
    assert group["best_platform"] == "Flipkart"
    assert group["best_price"] == "\u20b954,999"


def test_same_iphone_merges_across_amazon_flipkart_myntra():
    amazon = _offer(
        "Amazon",
        "Apple iPhone 15 (Black, 128 GB)",
        74999.0,
        "https://www.amazon.in/dp/B0IPH15128",
        product_id="B0IPH15128",
        product_key="apple-iphone-15-128gb-amazon",
    )
    flipkart = _offer(
        "Flipkart",
        "Apple iPhone 15 (Black 128 GB)",
        69999.0,
        "https://www.flipkart.com/apple-iphone-15/p/itm?pid=MOBIPH15",
        product_id="MOBIPH15",
        product_key="apple-iphone-15-128gb-flipkart",
    )
    myntra = _offer(
        "Myntra",
        "Apple iPhone 15 (Black, 128 GB)",
        70999.0,
        "https://www.myntra.com/mobiles/apple/IPH15MN/buy",
        product_id="IPH15MN",
        product_key="apple-iphone-15-128gb-myntra",
    )

    (group,) = aggregate_products([amazon, flipkart, myntra])
    assert {o["platform"] for o in group["offers"]} == {"Amazon", "Flipkart", "Myntra"}


def test_storage_difference_keeps_cards_separate():
    amazon_128 = _offer(
        "Amazon", "Samsung Galaxy S24 5G (Onyx Black, 128 GB)", 59999.0,
        "https://www.amazon.in/dp/B0ONYX128", product_id="B0ONYX128",
    )
    flipkart_256 = _offer(
        "Flipkart", "Samsung Galaxy S24 5G (Onyx Black, 256 GB)", 64999.0,
        "https://www.flipkart.com/samsung-galaxy-s24/p/itm?pid=MOBONYX1",
        product_id="MOBONYX1",
    )

    results = aggregate_products([amazon_128, flipkart_256])
    assert len(results) == 2, "128GB and 256GB are different products"


def test_s24_and_s24_ultra_never_merge():
    base = _offer(
        "Flipkart", "Samsung Galaxy S24 5G (Onyx Black, 128 GB)", 54999.0,
        "https://www.flipkart.com/samsung-galaxy-s24/p/itm?pid=MOBONYX1",
        product_id="MOBONYX1",
    )
    ultra = _offer(
        "Amazon", "Samsung Galaxy S24 Ultra 5G (Titanium, 256 GB)", 89999.0,
        "https://www.amazon.in/dp/B0ULTRA256", product_id="B0ULTRA256",
    )

    results = aggregate_products([base, ultra])
    assert len(results) == 2


def test_same_amazon_asin_merges_colour_variants():
    """Same listing (shared ASIN) merges even when colours differ."""
    black = _offer(
        "Amazon", "Samsung Galaxy S24 5G (Onyx Black, 128 GB)", 59999.0,
        "https://www.amazon.in/dp/B0ONYX128?tag=dealcompare-21",
        product_id="B0ONYX128",
    )
    marble = _offer(
        "Amazon", "Samsung Galaxy S24 5G (Marble Gray, 128 GB)", 58999.0,
        "https://www.amazon.in/dp/B0ONYX128?th=1&psc=1",
        product_id="B0ONYX128",
    )

    (group,) = aggregate_products([black, marble])
    assert len(group["offers"]) == 2
    assert group["best_platform"] == "Amazon"


def test_similar_titles_alone_never_merge():
    """Regression: 'similar titles only' must never create a match.

    The titles below carry NO extractable variant attributes (no brand, model,
    storage, size, colour, apparel descriptors...), so identity degrades to the
    exact product_key.  Similar-but-different keys must NOT merge.
    """
    a = _offer(
        "Myntra", "Smartphone 5G", 14999.0,
        "https://www.myntra.com/smartphone-5g/buy",
        product_key="smartphone-5g-myntra",
    )
    b = _offer(
        "Ajio", "Smartphone 5G", 15999.0,
        "https://www.ajio.com/smartphone-5g/p/7",
        product_key="smartphone-5g-ajio",
    )

    results = aggregate_products([a, b])
    assert len(results) == 2, "no structure -> only exact product_key may merge"


def test_attribute_less_titles_merge_on_exact_shared_key():
    """The documented fallback: identical attribute-less title + SAME key -> merge."""
    a = _offer(
        "Myntra", "Smartphone 5G", 14999.0,
        "https://www.myntra.com/smartphone-5g/1/buy",
        product_key="smartphone-5g",
    )
    b = _offer(
        "Ajio", "Smartphone 5G", 15999.0,
        "https://www.ajio.com/smartphone-5g/2/p",
        product_key="smartphone-5g",
    )

    (group,) = aggregate_products([a, b])
    assert {o["platform"] for o in group["offers"]} == {"Myntra", "Ajio"}


# --- match_offer priority matrix (app/services/matching.py) -----------------

def _product_rows(*offers):
    return {
        f"p{i}": {
            "sku": serialize_sku(compute_sku(o)),
            "strong": serialize_strong(compute_strong(o)),
        }
        for i, o in enumerate(offers)
    }


def test_matching_rows_merge_same_iphone_across_marketplaces():
    stored = _product_rows(
        _offer("Flipkart", "Apple iPhone 15 (Black, 128 GB)", 69999.0,
               "https://www.flipkart.com/x/p/itm?pid=MOBIPH15", product_id="MOBIPH15",
               product_key="apple-iphone-15-128gb-fk"),
    )
    amazon = _offer(
        "Amazon", "Apple iPhone 15 (Black, 128 GB)", 74999.0,
        "https://www.amazon.in/dp/B0IPH15128", product_id="B0IPH15128",
        product_key="apple-iphone-15-128gb-amazon",
    )

    assert match_offer(amazon, stored) == "p0"


def test_matching_rows_strong_id_merges_across_platforms():
    """A marketplace product identity (ASIN / Flipkart PID) is the strongest
    signal: same listing merges even when the title omits an attribute the
    stored row states."""
    stored = _product_rows(
        _offer("Amazon", "Samsung Galaxy S24 5G (Onyx Black, 128 GB)", 59999.0,
               "https://www.amazon.in/dp/B0ONYX128?th=1", product_id="B0ONYX128"),
    )
    relisted = _offer(
        "Amazon", "Galaxy S24 5G (Onyx Black, 128 GB)", 58999.0,
        "https://www.amazon.in/dp/B0ONYX128?tag=dealcompare-21", product_id="B0ONYX128",
    )

    assert match_offer(relisted, stored) == "p0"


def test_matching_rows_storage_conflict_never_matches():
    stored = _product_rows(
        _offer("Amazon", "Samsung Galaxy S24 5G (Onyx Black, 128 GB)", 59999.0,
               "https://www.amazon.in/dp/B0ONYX128", product_id="B0ONYX128"),
    )
    bigger = _offer(
        "Amazon", "Samsung Galaxy S24 5G (Onyx Black, 256 GB)", 64999.0,
        "https://www.amazon.in/dp/B0ONYX256", product_id="B0ONYX256",
    )

    assert match_offer(bigger, stored) is None


def test_matching_rows_similar_titles_only_never_match():
    stored = _product_rows(
        _offer("Myntra", "Smartphone 5G", 14999.0,
               "https://www.myntra.com/smartphone-5g/buy",
               product_key="smartphone-5g-myntra"),
    )
    lookalike = _offer(
        "Ajio", "Smartphone 5G", 15999.0,
        "https://www.ajio.com/smartphone-5g/p/99",
        product_key="smartphone-5g-ajio",
    )

    # Attribute-less titles: distinct fallback product_keys -> NO match.
    assert match_offer(lookalike, stored) is None


def test_matching_rows_attribute_less_title_matches_exact_key_only():
    stored = _product_rows(
        _offer("Myntra", "Smartphone 5G", 14999.0,
               "https://www.myntra.com/smartphone-5g/1/buy",
               product_key="smartphone-5g"),
    )
    same_listing = _offer(
        "Ajio", "Smartphone 5G", 15999.0,
        "https://www.ajio.com/smartphone-5g/2/p",
        product_key="smartphone-5g",
    )
    different_key = _offer(
        "Ajio", "Smartphone 5G", 15999.0,
        "https://www.ajio.com/smartphone-5g/2/p",
        product_key="smartphone-5g-v2",
    )

    assert match_offer(same_listing, stored) == "p0"
    assert match_offer(different_key, stored) is None