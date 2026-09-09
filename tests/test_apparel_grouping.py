"""
Regression tests for generic apparel PRODUCT IDENTITY / GROUPING.

History: brand-less shirts used the electronics "first meaningful tokens"
fingerprint as identity, so titles such as

    "Men Regular Fit Solid Spread Collar Formal Shirt"
    "Men Regular Fit Solid Casual Formal Shirt"

collapsed into the SAME canonical SKU and were shown as 8 offers of one card
even though they are distinct garments.  This suite pins down the fixed
behaviour: identity for apparel is driven by concrete descriptors (fit,
pattern, collar, sleeve, fabric, style, descriptor, colour, size, pack), NOT by
the first few title tokens.

All fixtures are deterministic and offline; nothing depends on live websites.
"""
import pytest

from app.services.ranking_service import filter_irrelevant_products
from app.aggregator.aggregator import aggregate_products
from app.utils.text_utils import extract_variant_attributes


def _offer(title, platform, price, product_key, url):
    return {
        "title": title,
        "product_key": product_key,
        "platform": platform,
        "price_value": price,
        "price_display": f"\u20b9{int(price)}",
        "url": url,
        "image": "https://www.example.com/img.jpg",
    }


def _platforms_of(results):
    return {
        (g["title"], tuple(sorted({o["platform"] for o in g["offers"]})))
        for g in results
    }


# ---------------------------------------------------------------------------
# 1. The exact reported "shirts" regression: plural query survives relevance
#    AND distinct shirts must not be merged into one card.
# ---------------------------------------------------------------------------

def test_shirts_query_keeps_generic_shirts_and_does_not_merge_distinct_ones():
    q = "shirts"
    products = [
        _offer("Men Regular Fit Solid Spread Collar Formal Shirt", "Flipkart", 319,
               "men-regular-fit-solid-spread-collar-formal-shirt", "/p/a?pid=FK1"),
        _offer("Men Regular Fit Solid Casual Formal Shirt", "Flipkart", 349,
               "men-regular-fit-solid-casual-formal-shirt", "/p/b?pid=FK2"),
        _offer("Men Slim Fit Solid Cotton Shirt", "Flipkart", 499,
               "men-slim-fit-solid-cotton-shirt", "/p/c?pid=FK3"),
        _offer("Samsung Refrigerator 400L Double Door", "Flipkart", 39990,
               "samsung-refrigerator-400l", "/p/d?pid=FK4"),
    ]

    kept = filter_irrelevant_products(products, q)
    assert len(kept) == 3, "the 3 shirts survive relevance; refrigerator is dropped"

    cards = aggregate_products(kept)
    # refrigerator rejected by relevance, and the 3 shirts are 3 distinct cards.
    assert len(cards) == 3
    titles = {card["title"] for card in cards}
    assert any("Spread Collar" in t for t in titles)
    assert any("Casual Formal" in t for t in titles)
    assert any("Slim Fit Solid Cotton" in t for t in titles)


# ---------------------------------------------------------------------------
# 2. Two genuinely different generic shirts with the same initial words no
#    longer merge (the exact root cause).
# ---------------------------------------------------------------------------

def test_same_initial_words_different_collar_stay_separate():
    spread = _offer("Men Regular Fit Solid Spread Collar Formal Shirt", "Flipkart",
                    319, "k1", "/p/s?pid=FKSPREAD")
    band = _offer("Men Regular Fit Solid Band Collar Formal Shirt", "Flipkart",
                  349, "k2", "/p/b?pid=FBAND")

    cards = aggregate_products([spread, band])
    assert len(cards) == 2, "spread collar and band collar are different shirts"


def test_same_initial_words_casual_descriptor_stays_separate():
    spread = _offer("Men Regular Fit Solid Spread Collar Formal Shirt", "Flipkart",
                    319, "k1", "/p/x?pid=FK1")
    casual = _offer("Men Regular Fit Solid Casual Formal Shirt", "Flipkart",
                    349, "k2", "/p/y?pid=FK2")

    cards = aggregate_products([spread, casual])
    assert len(cards) == 2, "spread-collar and casual shirts are different"


# ---------------------------------------------------------------------------
# 3. Same product across Flipkart/Amazon still merges when identity is
#    genuinely equivalent (including when one retailer spells it more briefly).
# ---------------------------------------------------------------------------

def test_identical_apparel_across_stores_merges():
    flipkart = _offer("Men Slim Fit Solid Cotton Shirt", "Flipkart", 499,
                      "fk-slim-cotton", "/p/f?pid=FKCOT")
    amazon = _offer("Men Slim Fit Solid Cotton Shirt", "Amazon", 529,
                    "amz-slim-cotton", "https://www.amazon.in/dp/B0FK100")

    cards = aggregate_products([flipkart, amazon])
    assert len(cards) == 1
    (card,) = cards
    assert {o["platform"] for o in card["offers"]} == {"Flipkart", "Amazon"}
    assert card["best_platform"] == "Flipkart"
    assert card["best_price"] == "\u20b9499"


def test_apparel_merges_when_one_retailer_omits_descriptor_words():
    flipkart = _offer("Men Slim Fit Solid Cotton Shirt", "Flipkart", 499,
                      "fk-full", "/p/f?pid=FKDESC")
    amazon = _offer("Men Slim Fit Shirt", "Amazon", 529,
                    "amz-brief", "https://www.amazon.in/dp/B0BRIEF")

    cards = aggregate_products([flipkart, amazon])
    assert len(cards) == 1, "omitting solid/cotton must not split the same shirt"


# ---------------------------------------------------------------------------
# 4. Different colour variants remain separate when colour is known.
# ---------------------------------------------------------------------------

def test_apparel_colour_variants_stay_separate():
    blue = _offer("Men Regular Fit Formal Shirt (Blue)", "Flipkart", 399,
                  "blue", "/p/blue?pid=BLUE")
    black = _offer("Men Regular Fit Formal Shirt (Black)", "Flipkart", 399,
                   "black", "/p/black?pid=BLACK")

    assert extract_variant_attributes(blue["title"])["color"] == "blue"
    assert extract_variant_attributes(black["title"])["color"] == "black"
    cards = aggregate_products([blue, black])
    assert len(cards) == 2


# ---------------------------------------------------------------------------
# 5. Different size / pack / quantity remain separate.
# ---------------------------------------------------------------------------

def test_apparel_pack_count_stays_separate():
    pack2 = _offer("Men Casual Cotton Socks (Pack of 2)", "Flipkart", 199,
                   "pak2", "/p/p2?pid=P2")
    pack8 = _offer("Men Casual Cotton Socks (Pack of 8)", "Flipkart", 349,
                   "pak8", "/p/p8?pid=P8")

    assert extract_variant_attributes(pack2["title"])["pack_count"] == 2
    assert extract_variant_attributes(pack8["title"])["pack_count"] == 8
    cards = aggregate_products([pack2, pack8])
    assert len(cards) == 2


def test_apparel_clothing_size_stays_separate():
    m = _offer("Men Slim Fit Solid Shirt (M)", "Flipkart", 349, "k-m", "/p/m?pid=MSIZE")
    l = _offer("Men Slim Fit Solid Shirt (L)", "Flipkart", 349, "k-l", "/p/l?pid=LSIZE")

    assert extract_variant_attributes(m["title"])["clothing_size"] == "M"
    assert extract_variant_attributes(l["title"])["clothing_size"] == "L"
    cards = aggregate_products([m, l])
    assert len(cards) == 2


# ---------------------------------------------------------------------------
# 6 & 7. Electronics grouping and chipset/model/storage/RAM do not regress.
# ---------------------------------------------------------------------------

def test_electronics_brand_model_identity_unchanged():
    iphone = _offer("Apple iPhone 15 (128 GB) - Black", "Amazon", 79999,
                    "apple-iphone-15-128gb", "https://www.amazon.in/dp/B0IPHONE")
    attrs = extract_variant_attributes(iphone["title"])
    assert attrs["brand"] == "apple"
    assert attrs["model"]  # the electronics model identity is still populated
    assert attrs["storage"] == "128gb"
    assert attrs["color"] == "black"
    # apparel attributes must remain untouched for electronics
    assert attrs["fit"] is None
    assert attrs["pattern"] is None
    assert attrs["collar"] is None
    assert attrs["descriptor"] is None


def test_electronics_variants_still_split_and_cross_store_still_merges():
    snap = _offer("Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
                  "Flipkart", 49999, "s24-snap", "/p/s24?pid=SNAP")
    exy = _offer("Samsung Galaxy S24 Exynos 5G (Amber Yellow, 128 GB)",
                 "Flipkart", 55999, "s24-exy", "/p/s24e?pid=EXY")
    amber_amazon = _offer("Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
                          "Amazon", 50999, "s24-amz", "https://www.amazon.in/dp/B0S24")

    # Exynos vs Snapdragon must stay separate...
    assert len(aggregate_products([snap, exy])) == 2
    # ...while the identical Snapdragon SKU merges across stores with the
    # Amazon one, keeping the cheapest as best.
    cards = aggregate_products([snap, amber_amazon])
    assert len(cards) == 1
    (card,) = cards
    assert {o["platform"] for o in card["offers"]} == {"Flipkart", "Amazon"}
    assert card["best_platform"] == "Flipkart"


# ---------------------------------------------------------------------------
# 8. Existing non-electronics (wallet / handbag / trolley) grouping unchanged.
# ---------------------------------------------------------------------------

def test_generic_non_apparel_grouping_unchanged():
    wallet = _offer("Men Brown Genuine Leather Wallet", "Flipkart", 279,
                    "wallet", "/p/w?pid=WAL")
    card_holder = _offer("Men Casual Black Genuine Leather Card Holder", "Flipkart",
                         269, "cardholder", "/p/ch?pid=CH")

    cards = aggregate_products([wallet, card_holder])
    assert len(cards) == 2
    titles = {c["title"] for c in cards}
    assert any("Wallet" in t for t in titles)
    assert any("Card Holder" in t for t in titles)


# ---------------------------------------------------------------------------
# End-to-end sketch: relevant shirts flow through filter -> aggregate with the
# freedom to run as many offers as come from the source.
# ---------------------------------------------------------------------------

def test_many_distinct_shirts_make_many_cards_with_single_offers():
    shirts = [
        _offer("Men Slim Fit Solid Cotton Casual Shirt", "Flipkart", 300, "k0", "/p/0?pid=FK0"),
        _offer("Men Regular Fit Solid Denim Party Shirt", "Flipkart", 400, "k1", "/p/1?pid=FK1"),
        _offer("Men Relaxed Fit Checked Formal Shirt", "Flipkart", 350, "k2", "/p/2?pid=FK2"),
        _offer("Men Slim Fit Striped Linen Office Shirt", "Flipkart", 450, "k3", "/p/3?pid=FK3"),
        _offer("Men Regular Fit Solid Multicolor Casual Shirt", "Flipkart", 380, "k4", "/p/4?pid=FK4"),
        _offer("Men Tailored Fit Oxford Wedding Shirt", "Flipkart", 620, "k5", "/p/5?pid=FK5"),
        _offer("Men Slim Fit Printed Sports Shirt", "Flipkart", 420, "k6", "/p/6?pid=FK6"),
        _offer("Men Regular Fit Classic Formal Shirt", "Flipkart", 340, "k7", "/p/7?pid=FK7"),
    ]
    kept = filter_irrelevant_products(shirts, "shirts")
    assert len(kept) == 8, "all 8 distinct shirts survive relevance"
    cards = aggregate_products(kept)
    assert len(cards) == 8, "each genuinely different shirt is its own card, no over-merging"
    assert all(len(c["offers"]) == 1 for c in cards)
    assert len({c["title"] for c in cards}) == 8


