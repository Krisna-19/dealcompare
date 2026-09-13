"""
Catalog matching tests (app/services/matching.py).

The matching rules must agree EXACTLY with the /search aggregator: same-listing
strong ids merge across colours; attribute-compatible SKUs merge across stores;
genuinely different variants (RAM, ...) stay separate; identity is
deterministic across re-scrapes and serialization round-trips.
"""

from app.services.matching import (
    build_offer_id,
    compute_sku,
    compute_strong,
    deserialize_sku,
    deserialize_strong,
    match_offer,
    match_offer_to_product,
    serialize_sku,
    serialize_strong,
)


def _row(offer):
    """Shaped like a stored product dict (the subset matching reads)."""
    return {
        "sku": serialize_sku(compute_sku(offer)),
        "strong": serialize_strong(compute_strong(offer)),
    }


def _amazon_offer(title="Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
                  asin="B0BLAHBLAH", color=None):
    if color:
        title = f"Samsung Galaxy S24 5G ({color}, 128 GB) (8 GB RAM)"
    return {
        "title": title,
        "product_key": "samsung-galaxy-s24-5g",
        "platform": "Amazon",
        "price_value": 62999.0,
        "price_display": "\u20b962,999",
        "url": f"https://www.amazon.in/dp/{asin}",
        "image": "",
    }


def _flipkart_offer(title="Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
                    pid="MOBX24"):
    return {
        "title": title,
        "product_key": "samsung-galaxy-s24-5g",
        "platform": "Flipkart",
        "price_value": 64999.0,
        "price_display": "\u20b964,999",
        "url": f"https://www.flipkart.com/galaxy-s24/p/itm{pid}?pid={pid}",
        "image": "",
    }


def test_amazon_dp_offer_strong_is_asin():
    assert compute_strong(_amazon_offer()) == ("asin", "B0BLAHBLAH")


def test_flipkart_api_offer_strong_is_product_id():
    offer = _flipkart_offer(pid="MOBH7GF3KQFTCEG5")
    offer["product_id"] = "MOBH7GF3KQFTCEG5"
    assert compute_strong(offer) == ("flipkart:product_id", "MOBH7GF3KQFTCEG5")


def test_serialize_deserialize_round_trip():
    sku = compute_sku(_amazon_offer())
    assert deserialize_sku(serialize_sku(sku)) == sku

    strong = compute_strong(_amazon_offer())
    assert deserialize_strong(serialize_strong(strong)) == strong
    # None strong survives the round trip as None (JSON-safe).
    assert deserialize_strong(serialize_strong(None)) is None


def test_build_offer_id_deterministic_and_price_stable():
    # Same listing re-scraped (even a price change) keeps the same id so the
    # offer row + price history are updated rather than duplicated.
    assert build_offer_id(_amazon_offer(), compute_strong(_amazon_offer())) == \
        build_offer_id({**_amazon_offer(), "price_value": 61999.0},
                       compute_strong(_amazon_offer()))
    assert build_offer_id(_amazon_offer(), compute_strong(_amazon_offer())) == \
        "amazon:asin/B0BLAHBLAH"


def test_match_same_listing_different_colors_merges():
    black = _amazon_offer(color="Onyx Black")
    blue = _amazon_offer(color="Marble Gray")  # same listing page, selectable colour
    sku_b, strong_b = compute_sku(black), compute_strong(black)
    sku_l, strong_l = compute_sku(blue), compute_strong(blue)

    assert match_offer_to_product(sku_l, strong_l, {"P1": _row(black)}) == "P1"


def test_match_cross_store_same_sku_merges():
    products = {"P1": _row(_amazon_offer())}
    flipkart = _flipkart_offer()  # different strong id (product_id) ...
    assert match_offer_to_product(compute_sku(flipkart), compute_strong(flipkart),
                                  products) == "P1"  # ... but same SKU merges


def test_match_different_variant_stays_separate():
    products = {"P1": _row(_amazon_offer(title="Apple MacBook Pro (16 GB RAM, 512 GB SSD)"))}
    other = _amazon_offer(title="Apple MacBook Pro (8 GB RAM, 512 GB SSD)", asin="B0OTHEROTH")
    assert match_offer_to_product(compute_sku(other), compute_strong(other),
                                  products) is None


def test_match_offer_convenience():
    products = {"P1": _row(_amazon_offer())}
    assert match_offer(_flipkart_offer(), products) == "P1"
    assert match_offer(_amazon_offer(title="Apple MacBook Pro (8 GB RAM, 512 GB SSD)",
                                     asin="B0OTHEROTH"), products) is None