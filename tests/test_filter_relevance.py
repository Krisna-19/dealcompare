"""
Deterministic regression tests for the generic/search relevance filter.

These cover the fix to `filter_irrelevant_products` described in the audit:
generic/category queries such as "tshirt men" previously rejected *every*
product (from every store) because the whole query slug never equalled the
product title slug.  They must now keep genuinely relevant products while
still rejecting clearly unrelated ones, WITHOUT disturbing the existing
specific-SKU (electronics) matching or the aggregation layer.
"""
import pytest

from app.services.ranking_service import filter_irrelevant_products
from app.aggregator.aggregator import aggregate_products


def _offer(title, product_key, platform, price_value=1000.0):
    return {
        "title": title,
        "product_key": product_key,
        "platform": platform,
        "price_value": price_value,
        "price_display": f"\u20b9{int(price_value)}",
        "url": f"https://www.example.com/{platform.lower()}/{product_key}",
        "image": "https://www.example.com/img.jpg",
    }


def _kept_titles(results):
    return {r["title"] for r in results}


# ---------------------------------------------------------------------------
# CASE A — generic fashion query keeps genuinely relevant t-shirts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["tshirt men", "tshirt", "men tshirt"])
def test_case_a_generic_query_keeps_relevant_tshirts_from_all_stores(query):
    products = [
        # genuine t-shirts from all three stores
        _offer("Amazon Brand - Symbol Men's Regular Fit T-Shirt",
               "amazon-symbol-men-regular-fit-tshirt", "Amazon"),
        _offer("Levis Men Slim Fit T-Shirt",
               "levis-men-slim-fit-tshirt", "Flipkart"),
        _offer("AMUL COMFY Pack Of 2 Round Neck T-Shirt",
               "amul-comfy-pack-of-2-round-neck-tshirt", "Myntra"),
        # clearly unrelated / off-topic
        _offer("Apple iPhone 15 (128 GB) - Black",
               "apple-iphone-15-128gb", "Amazon"),
        _offer("Samsung Refrigerator 400L Double Door",
               "samsung-refrigerator-400l", "Flipkart"),
    ]

    kept = filter_irrelevant_products(products, query)

    kept_titles = _kept_titles(kept)
    # the three t-shirts survive relevance filtering
    assert any("T-Shirt" in t or "T-shirt" in t for t in kept_titles)
    assert any("Levis" in t for t in kept_titles)
    assert any("AMUL" in t for t in kept_titles)
    # genuinely unrelated products are still rejected
    assert not any("iPhone" in t for t in kept_titles)
    assert not any("Refrigerator" in t for t in kept_titles)


def test_case_a_men_tshirt_returns_only_tshirts_not_mere_shirts():
    """
    The filter must not become a pass-through for 'men': a casual shirt that
    shares only the weak token 'men' (but is not a t-shirt) stays rejected.
    """
    q = "tshirt men"
    products = [
        _offer("Roadster Men Solid Casual Shirt", "roadster-men-solid-shirt", "Flipkart"),
        _offer("Levis Men Slim Fit T-Shirt", "levis-men-slim-fit-tshirt", "Flipkart"),
    ]
    kept = filter_irrelevant_products(products, q)
    kept_titles = _kept_titles(kept)
    assert any("T-Shirt" in t for t in kept_titles)
    assert not any("Casual Shirt" in t for t in kept_titles)


# ---------------------------------------------------------------------------
# CASE B — unrelated products are still rejected for the generic query
# ---------------------------------------------------------------------------

def test_case_b_generic_query_rejects_clearly_unrelated_products():
    q = "tshirt men"
    unrelated = [
        _offer("Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
               "samsung-s24-128gb", "Myntra"),
        _offer("LG Washing Machine 7kg", "lg-washing-machine-7kg", "Flipkart"),
        _offer("Men's Wrist Watch Analog", "men-wrist-watch-analog", "Amazon"),
        _offer("Sony WH-1000XM5 Headphones", "sony-wh-1000xm5", "Flipkart"),
        _offer("Roadster Men Solid Casual Shirt", "roadster-men-solid-shirt", "Flipkart"),
    ]
    kept = filter_irrelevant_products(unrelated, q)
    # nothing unrelated shares a meaningful token ('tshirt') with the query
    assert len(kept) == 0


def test_case_b_one_shared_weak_word_is_not_enough():
    """
    'women'/'for' etc. must not, by themselves, make an unrelated product
    relevant (requirement 7).  Only t-shirts match 'tshirt men'.
    """
    q = "tshirt women"
    products = [
        _offer("Women's Cotton Kurti", "women-cotton-kurti", "Ajio"),
        _offer("Women's Henley Neck T-Shirt", "women-henley-neck-tshirt", "Myntra"),
    ]
    kept = filter_irrelevant_products(products, q)
    kept_titles = _kept_titles(kept)
    # the t-shirt is relevant, the kurti (shares only 'women') is not
    assert any("T-Shirt" in t for t in kept_titles)
    assert not any("Kurti" in t for t in kept_titles)


# ---------------------------------------------------------------------------
# CASE C — specific electronics query keeps existing S24 behaviour unchanged
# ---------------------------------------------------------------------------

def test_case_c_s24_search_preserves_exact_match_behavior():
    q = "samsung galaxy s24"
    products = [
        _offer("Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
               "samsung-s24-128gb", "Amazon"),
        _offer("Samsung Galaxy S26 5G (Onyx Black, 128 GB)",
               "samsung-s26-128gb", "Flipkart"),
        _offer("Apple iPhone 15 (128 GB) - Black", "apple-iphone-15-128gb", "Flipkart"),
    ]

    kept = filter_irrelevant_products(products, q)
    kept_titles = _kept_titles(kept)

    assert any("S24 5G" in t for t in kept_titles)
    # S26 and the unrelated iPhone must still be rejected
    assert not any("S26" in t for t in kept_titles)
    assert not any("iPhone" in t for t in kept_titles)


def test_case_c_s24_with_storage_keeps_s24_and_rejects_s23():
    q = "samsung galaxy s24 128gb"
    products = [
        _offer("Samsung Galaxy S24 5G (Onyx Black, 128 GB)", "samsung-s24-128gb", "Flipkart"),
        _offer("Samsung Galaxy S23 5G (Onyx Black, 128 GB)", "samsung-s23-128gb", "Amazon"),
    ]
    kept = filter_irrelevant_products(products, q)
    kept_titles = _kept_titles(kept)
    assert any("S24 5G" in t for t in kept_titles)
    assert not any("S23" in t for t in kept_titles)


# ---------------------------------------------------------------------------
# CASE D — variant separation: 128GB vs 256GB survive filtering as 2 cards
# ---------------------------------------------------------------------------

def test_case_d_s24_128gb_and_256gb_filter_keeps_both_and_stay_separate():
    q = "samsung galaxy s24"
    products = [
        _offer("Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
               "samsung-s24-128gb", "Flipkart", 49999.0),
        _offer("Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)",
               "samsung-s24-256gb", "Flipkart", 55999.0),
    ]

    # Both are valid S24 and must survive relevance filtering...
    kept = filter_irrelevant_products(products, q)
    assert len(kept) == 2

    # ...but the aggregation layer keeps them as two separate product cards.
    groups = aggregate_products(kept)
    assert len(groups) == 2
    by_title = {g["title"] for g in groups}
    assert any("128 GB" in t for t in by_title)
    assert any("256 GB" in t for t in by_title)


# ---------------------------------------------------------------------------
# CASE E — cross-store aggregation: same SKU remains one card
# ---------------------------------------------------------------------------

def test_case_e_same_sku_across_stores_aggregates_to_one_card():
    q = "samsung galaxy s24"
    products = [
        _offer("Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
               "samsung-s24-onyx-black-128gb", "Amazon", 51999.0),
        _offer("Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
               "samsung-s24-onyx-black-128gb", "Flipkart", 49999.0),
        _offer("Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
               "samsung-s24-onyx-black-128gb", "Myntra", 52499.0),
    ]

    # all three survive relevance filtering
    kept = filter_irrelevant_products(products, q)
    assert len(kept) == 3

    # and they collapse into ONE product card with three store offers
    groups = aggregate_products(kept)
    assert len(groups) == 1
    assert sorted(o["platform"] for o in groups[0]["offers"]) == ["Amazon", "Flipkart", "Myntra"]


# ---------------------------------------------------------------------------
# CASE F — a genuine Myntra fashion offer flows through a generic query
# ---------------------------------------------------------------------------

def test_case_f_myntra_tshirt_offer_survives_generic_filter():
    q = "tshirt men"
    products = [
        _offer("AMUL COMFY Pack Of 2 Round Neck T-Shirt",
               "amul-comfy-pack-of-2-round-neck-tshirt", "Myntra"),
        _offer("Levis Men Brand Logo Printed Slim Fit T-shirt",
               "levis-men-brand-logo-printed-slim-fit-tshirt", "Myntra"),
    ]
    kept = filter_irrelevant_products(products, q)
    kept_titles = _kept_titles(kept)
    assert any("AMUL" in t for t in kept_titles)
    assert any("Levis" in t for t in kept_titles)


# ---------------------------------------------------------------------------
# CASE G — specific electronics query keeps genuine model accessories
# ---------------------------------------------------------------------------
# For "samsung galaxy s24" the relevance filter must keep the actual S24
# phone AND genuine S24 accessories (cases/back covers whose title names the
# S24 model), while still rejecting different/sub-variant models (S25, S24
# Ultra, S24 Plus, S24 FE, iPhone, Turbo...) and leaving aggregation and the
# Exynos/Snapdragon split untouched.

def test_case_g_s24_phone_and_accessories_are_kept():
    q = "samsung galaxy s24"
    products = [
        # actual S24 phone
        _offer("Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
               "samsung-s24-128gb", "Amazon"),
        # genuine S24 accessories
        _offer("QRIOH Samsung Galaxy S24 5G Back Case Mobile Accessories",
               "samsung-qrioh-s24-back-case", "Myntra"),
        _offer("Luxury Kase Samsung Galaxy S24 5G Case",
               "samsung-luxury-kase-s24-case", "Myntra"),
        _offer("SPRIG Samsung Galaxy S24 Back Cover",
               "samsung-sprig-s24-back-cover", "Myntra"),
    ]
    kept = filter_irrelevant_products(products, q)
    kept_titles = _kept_titles(kept)
    assert any("S24 5G Snapdragon" in t for t in kept_titles)
    assert any("S24 5G Back Case" in t for t in kept_titles)
    assert any("S24 5G Case" in t for t in kept_titles)
    assert any("S24 Back Cover" in t for t in kept_titles)


def test_case_g_s24_sub_variants_are_rejected():
    q = "samsung galaxy s24"
    products = [
        _offer("CASE CREATION Samsung Galaxy S24 Ultra 5G Bumper Case",
               "samsung-case-creation-s24-ultra", "Myntra"),
        _offer("Luxury Kase Samsung Galaxy S24 Plus Back Case Mobile Accessories",
               "samsung-luxury-kase-s24-plus-back", "Myntra"),
        _offer("SPRIG Samsung S24 fe Back Cover", "samsung-sprig-s24-fe-back", "Myntra"),
        _offer("Samsung Galaxy S24 Ultra 5G (Onyx Black, 128 GB)",
               "samsung-s24-ultra-128gb", "Flipkart"),
    ]
    kept = filter_irrelevant_products(products, q)
    assert len(kept) == 0


def test_case_g_different_phone_models_are_rejected():
    q = "samsung galaxy s24"
    products = [
        _offer("Galaxy S25 5G Smartphone with Galaxy AI", "samsung-s25", "Amazon"),
        _offer("Samsung Galaxy S25 FE 5G Smartphone with Galaxy AI", "samsung-s25-fe", "Flipkart"),
        _offer("Apple iPhone 15 (128 GB) - Black", "apple-iphone-15-128gb", "Flipkart"),
        _offer("Turbo 5 (8GB + 256GB) Asphalt Black", "turbo-5-256gb", "Amazon"),
    ]
    kept = filter_irrelevant_products(products, q)
    assert len(kept) == 0


def test_case_g_unrelated_myntra_accessory_is_rejected():
    """
    An accessory whose title does NOT name the queried S24 model must still
    be rejected (generic "Samsung back case", chargers, unrelated items).
    """
    q = "samsung galaxy s24"
    products = [
        _offer("PEEPERLY Women Samsung Back Case", "samsung-peeperly-women-back-case", "Myntra"),
        _offer("DR VAKU Wired USB-C Charger - 20W", "dr-vaku-wired-usb-c-charger", "Myntra"),
        _offer("Samsung 24W Fast Charger", "samsung-24w-fast-charger", "Myntra"),
    ]
    kept = filter_irrelevant_products(products, q)
    assert len(kept) == 0


def test_case_g_iphone_query_still_matches_exactly():
    """
    The accessory tolerance is anchored on the query's own model token, so a
    query for iPhone 15 still keeps iPhone 15 and rejects iPhone 14 / S24.
    """
    q = "iphone 15"
    products = [
        _offer("Apple iPhone 15 (128 GB) - Black", "apple-iphone-15-128gb", "Flipkart"),
        _offer("Apple iPhone 14 (128 GB) - Blue", "apple-iphone-14-128gb", "Flipkart"),
        _offer("Samsung Galaxy S24 5G (Onyx Black, 128 GB)", "samsung-s24-128gb", "Amazon"),
    ]
    kept = filter_irrelevant_products(products, q)
    kept_titles = _kept_titles(kept)
    assert any("iPhone 15" in t for t in kept_titles)
    assert not any("iPhone 14" in t for t in kept_titles)
    assert not any("S24" in t for t in kept_titles)


def test_case_g_chipset_and_grouping_behavior_unchanged():
    """
    The relevance fix must NOT merge Exynos and Snapdragon variants. Both S24
    Exynos and S24 Snapdragon Amber Yellow 256 GB survive relevance filtering
    and STILL become two separate product cards after aggregation (341).
    """
    q = "samsung galaxy s24"
    products = [
        _offer("Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)",
               "samsung-s24-256gb", "Flipkart", 55999.0),
        _offer("Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)",
               "samsung-s24-256gb", "Flipkart", 55999.0),
    ]

    kept = filter_irrelevant_products(products, q)
    assert len(kept) == 2, "both chipset variants must survive relevance filtering"

    groups = aggregate_products(kept)
    assert len(groups) == 2, "Exynos and Snapdragon must remain separate cards"
    by_title = {g["title"] for g in groups}
    assert any("Exynos" in t for t in by_title)
    assert any("Snapdragon" in t for t in by_title)


# ---------------------------------------------------------------------------
# CASE H — variant separation: base S24 vs Ultra / Plus / FE.
# ---------------------------------------------------------------------------


def _s24_pool():
    """Phone + genuine-accessory titles for every S24 sub-variant."""
    return [
        _offer("Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
               "samsung-s24-128gb", "Flipkart", 55999.0),
        _offer("Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)",
               "samsung-s24-256gb", "Flipkart", 59999.0),
        _offer("CaseCreation Samsung Galaxy S24 Ultra 5G (Titanium Black, 256 GB)",
               "samsung-s24-ultra-256gb", "Flipkart", 79999.0),
        _offer("Samsung Galaxy S24+ 5G (Onyx Black, 256 GB)",
               "samsung-s24-plus-256gb", "Flipkart", 74999.0),
        _offer("Samsung Galaxy S24 Plus 5G (Onyx Black, 256 GB)",
               "samsung-s24plus-256gb", "Flipkart", 74999.0),
        _offer("Samsung Galaxy S24 FE 5G (Graphite, 128 GB)",
               "samsung-s24-fe-128gb", "Flipkart", 42999.0),
        _offer("Samsung Galaxy S25 5G Smartphone", "samsung-s25-256gb",
               "Flipkart", 89999.0),
    ]


def test_case_h_base_s24_query_keeps_base_and_accessories_rejects_variants():
    pool = _s24_pool()
    pool.append(_offer("Qrioh Samsung S24 Back Case Clear", "qrioh-s24-back-case",
                       "Myntra", 299.0))
    kept = filter_irrelevant_products(pool, "samsung galaxy s24")
    kept_titles = _kept_titles(kept)
    assert any("S24 5G Snapdragon" in t for t in kept_titles)
    assert any("S24 Exynos" in t for t in kept_titles)
    assert any("S24 Back Case" in t for t in kept_titles)
    assert not any("Ultra" in t for t in kept_titles)
    assert not any("S24+" in t for t in kept_titles)
    assert not any("S24 Plus" in t for t in kept_titles)
    assert not any("S24 FE" in t for t in kept_titles)


def test_case_h_ultra_query_keeps_only_ultra():
    kept = filter_irrelevant_products(_s24_pool(), "samsung galaxy s24 ultra")
    kept_titles = _kept_titles(kept)
    assert len(kept_titles) == 1
    assert next(iter(kept_titles)) == (
        "CaseCreation Samsung Galaxy S24 Ultra 5G (Titanium Black, 256 GB)")


def test_case_h_plus_query_keeps_only_plus_spellings():
    kept = filter_irrelevant_products(_s24_pool(), "samsung galaxy s24 plus")
    kept_titles = _kept_titles(kept)
    assert len(kept_titles) == 2
    assert any("S24+" in t for t in kept_titles)
    assert any("S24 Plus" in t for t in kept_titles)
    assert not any("S24 5G Snapdragon" in t for t in kept_titles)
    assert not any("Ultra" in t for t in kept_titles)
    assert not any("S24 FE" in t for t in kept_titles)


def test_case_h_fe_query_keeps_only_fe():
    kept = filter_irrelevant_products(_s24_pool(), "samsung galaxy s24 fe")
    kept_titles = _kept_titles(kept)
    assert len(kept_titles) == 1
    assert next(iter(kept_titles)) == (
        "Samsung Galaxy S24 FE 5G (Graphite, 128 GB)")
    assert not any("S24+" in t for t in kept_titles)


def test_case_h_s24_plus_is_canonicalised_to_s24_plus():
    from app.utils.text_utils import extract_product_info
    model = extract_product_info("Samsung Galaxy S24+ 5G (Onyx Black, 256 GB)")[1]
    assert model == "s24-plus"
    model2 = extract_product_info(
        "Samsung Galaxy S24 Plus 5G (Onyx Black, 256 GB)")[1]
    assert model2 == "s24-plus"


# ---------------------------------------------------------------------------
# CASE I — brand + laptop-type queries ("laptop asus" / "asus laptop") keep
# only that brand's actual laptop devices, never accessories or other brands.
# ---------------------------------------------------------------------------

_LAPTOP_POOL = [
    _offer("ASUS Vivobook 15 Intel Core i3 12th Gen 15.6 inch Laptop",
           "asus-vivobook-15", "Amazon", 32990),
    _offer("ASUS ExpertBook B1400 Thin and Light Laptop",
           "asus-expertbook-b1400", "Amazon", 40990),
    _offer("ASUS TUF Gaming F15 Laptop Core i5",
           "asus-tuf-f15", "Flipkart", 56990),
    _offer("ASUS Zenbook 14 OLED Core Ultra 7",
           "asus-zenbook-14", "Amazon", 89990),
    _offer("ASUS Chromebook Plus CX34 Intel Core i3 14 inch",
           "asus-chromebook-cx34", "Flipkart", 24990),
    _offer("ASUS Laptop Backpack 15.6 Inch Waterproof",
           "asus-laptop-backpack", "Amazon", 1299),
    _offer("ASUS Laptop Bag for Men", "asus-laptop-bag-men", "Myntra", 899),
    _offer("ASUS Laptop Sleeve 15.6 inch", "asus-laptop-sleeve", "Myntra", 799),
    _offer("ASUS Backpack for College", "asus-backpack-college", "Flipkart", 999),
    _offer("ASUS Wireless Mouse", "asus-wireless-mouse", "Amazon", 1499),
    _offer("ASUS Keyboard", "asus-keyboard", "Flipkart", 2499),
    _offer("ASUS Monitor 24 inch", "asus-monitor-24", "Amazon", 10990),
    _offer("HP Laptop 15s Core i5", "hp-laptop-15s", "Flipkart", 38990),
    _offer("Lenovo IdeaPad Slim Laptop", "lenovo-ideapad-slim", "Amazon", 35990),
]


@pytest.mark.parametrize("query", ["laptop asus", "asus laptop"])
def test_case_i_brand_laptop_query_keeps_only_asus_laptops(query):
    kept = filter_irrelevant_products(_LAPTOP_POOL, query)
    kept_titles = {t for t in _kept_titles(kept)}

    # ASUS laptops (incl. Chromebook as a laptop) are kept.
    assert any("ASUS Vivobook" in t for t in kept_titles)
    assert any("ASUS ExpertBook" in t for t in kept_titles)
    assert any("ASUS TUF Gaming" in t for t in kept_titles)
    assert any("ASUS Zenbook" in t for t in kept_titles)
    assert any("ASUS Chromebook" in t for t in kept_titles)

    # ASUS accessories and other-brand laptops are removed.
    assert kept_titles == {
        "ASUS Vivobook 15 Intel Core i3 12th Gen 15.6 inch Laptop",
        "ASUS ExpertBook B1400 Thin and Light Laptop",
        "ASUS TUF Gaming F15 Laptop Core i5",
        "ASUS Zenbook 14 OLED Core Ultra 7",
        "ASUS Chromebook Plus CX34 Intel Core i3 14 inch",
    }


@pytest.mark.parametrize("query", ["laptop asus", "asus laptop"])
def test_case_i_brand_laptop_query_removes_accessories_and_other_brands(query):
    kept_titles = _kept_titles(filter_irrelevant_products(_LAPTOP_POOL, query))
    assert not any("Backpack" in t for t in kept_titles)
    assert not any("Laptop Bag" in t for t in kept_titles)
    assert not any("Sleeve" in t for t in kept_titles)
    assert not any("Mouse" in t for t in kept_titles)
    assert not any("Keyboard" in t for t in kept_titles)
    assert not any("Monitor" in t for t in kept_titles)
    assert not any("HP Laptop" in t for t in kept_titles)
    assert not any("Lenovo" in t for t in kept_titles)


# ---------------------------------------------------------------------------
# CASE J — preservation: "laptop" (all brands), "asus" (all ASUS products),
# and "laptop bag" (explicit accessory query) keep their existing behavior.
# ---------------------------------------------------------------------------

def test_case_j_laptop_alone_is_not_asus_only():
    kept_titles = _kept_titles(filter_irrelevant_products(_LAPTOP_POOL, "laptop"))
    assert any("HP Laptop" in t for t in kept_titles)
    assert any("Lenovo" in t for t in kept_titles)
    assert any("ASUS Vivobook" in t for t in kept_titles)


def test_case_j_asus_alone_keeps_all_asus_products_including_accessories():
    kept_titles = _kept_titles(filter_irrelevant_products(_LAPTOP_POOL, "asus"))
    assert any("ASUS Wireless Mouse" in t for t in kept_titles)
    assert any("ASUS Keyboard" in t for t in kept_titles)
    assert any("ASUS Backpack" in t for t in kept_titles)
    assert any("ASUS Vivobook" in t for t in kept_titles)


def test_case_j_laptop_bag_explicit_still_returns_bags():
    kept_titles = _kept_titles(filter_irrelevant_products(_LAPTOP_POOL, "laptop bag"))
    assert any("Laptop Bag" in t for t in kept_titles)
    assert any("Laptop Backpack" in t for t in kept_titles)
