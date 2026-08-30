"""
Regression tests for PRODUCT IDENTITY / GROUPING correctness.

Covers the exact failures observed in the "Samsung Galaxy S24" search UI:

  - Z11 offers must never appear under the Turbo 5 card (or vice versa).
  - Amber Yellow / Onyx Black / Cobalt Violet... are distinct SKUs.
  - Snapdragon / Exynos are distinct variants when explicitly identified.
  - 128GB / 256GB are distinct SKUs.
  - Exact duplicate scraper records are still deduplicated.
  - Same-SKU offers across listings/stores keep their own View Deal URLs.
  - Every card's offers[] must resolve to a single SKU.
"""
from app.aggregator.aggregator import aggregate_products
from app.utils.text_utils import extract_variant_attributes


def _sku_of(offer):
    """Re-derive the SKU identity the same way the aggregator does."""
    attrs = extract_variant_attributes(offer.get("title") or "")
    parts = tuple(
        (label, value)
        for label, value in (
            ("brand", attrs["brand"]),
            ("model", attrs["model"]),
            ("ram", attrs["ram"]),
            ("storage", attrs["storage"]),
            ("processor", attrs["processor"]),
            ("color", attrs["color"]),
            ("edition", attrs["edition"]),
            ("model_no", attrs["model_no"]),
        )
        if value
    )
    return parts or (("key", (offer.get("product_key") or "").lower()),)


def _all_offers(results):
    return [o for group in results for o in group["offers"]]


# --- 1. Z11 + Turbo 5 must remain separate -------------------------------

def test_z11_and_turbo_5_never_share_a_card(make_product):
    z11 = make_product(
        platform="Amazon",
        product_key="z11-5g-celestial-blue-8gb-ram",
        title="Z11 5G (Celestial Blue, 8GB RAM, 128GB Storage) | India's 1st MediaTek Dimensity 7200 Processor",
        price_value=39999.0,
        price_display="\u20b939,999",
        url="https://www.amazon.in/dp/B0Z11PROD11",
    )
    turbo = make_product(
        platform="Amazon",
        product_key="turbo-5-8gb-256gb-asphalt-black",
        title="Turbo 5 (8GB + 256GB) Asphalt Black | Dimensity 8500 Ultra",
        price_value=41999.0,
        price_display="\u20b941,999",
        url="https://www.amazon.in/dp/B0TURBO5PROD",
    )

    results = aggregate_products([z11, turbo])

    assert len(results) == 2, "Z11 and Turbo 5 must be separate product cards"
    titles = {g["title"] for g in results}
    assert any("Z11" in t for t in titles)
    assert any("Turbo 5" in t for t in titles)
    assert len({o["platform"] for o in _all_offers(results)}) == 1


# --- 2. Amber Yellow 128 + Onyx Black 128 must stay separate -------------

def test_s24_amber_yellow_128_and_onyx_black_128_are_separate(make_product):
    amber = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        price_display="\u20b949,999",
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/ita?pid=AMBER128",
    )
    onyx = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        price_value=49999.0,
        price_display="\u20b949,999",
        url="/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/itb?pid=ONYX128",
    )

    results = aggregate_products([amber, onyx])

    assert len(results) == 2
    assert len({g["title"] for g in results}) == 2
    assert all(len(g["offers"]) == 1 for g in results)


# --- 3. Cobalt Violet 256 vs Amber Yellow 256 must stay separate ---------

def test_s24_cobalt_violet_256_and_amber_yellow_256_are_separate(make_product):
    violet = make_product(
        platform="Flipkart",
        product_key="samsung-s24-256gb",
        title="Samsung Galaxy S24 5G Snapdragon (Cobalt Violet, 256 GB)",
        price_value=55999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-cobalt-violet-256-gb/p/itc?pid=VIOLET256",
    )
    amber = make_product(
        platform="Flipkart",
        product_key="samsung-s24-256gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)",
        price_value=55999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-256-gb/p/itd?pid=AMBER256",
    )

    results = aggregate_products([violet, amber])

    assert len(results) == 2
    assert {g["title"] for g in results} == {
        "Samsung Galaxy S24 5G Snapdragon (Cobalt Violet, 256 GB)",
        "Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)",
    }


# --- 4. Snapdragon vs Exynos must stay separate --------------------------

def test_snapdragon_and_exynos_variants_stay_separate(make_product):
    snapdragon = make_product(
        platform="Flipkart",
        product_key="samsung-s24-256gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)",
        price_value=55999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-256-gb/p/ite?pid=SNAPDA",
    )
    exynos = make_product(
        platform="Flipkart",
        product_key="samsung-s24-256gb",
        title="Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)",
        price_value=55999.0,
        url="/samsung-galaxy-s24-exynos-5g-amber-yellow-256-gb/p/itf?pid=EXYNOSB",
    )

    results = aggregate_products([snapdragon, exynos])

    assert len(results) == 2
    snap = next(g for g in results if "Snapdragon" in g["title"])
    exy = next(g for g in results if "Exynos" in g["title"])
    assert all("Exynos" not in o["title"] for o in snap["offers"])
    assert all("Snapdragon" not in o["title"] for o in exy["offers"])


# --- 5. 128GB vs 256GB must stay separate --------------------------------

def test_s24_128gb_and_256gb_stay_separate(make_product):
    small = make_product(
        platform="Flipkart",
        product_key="samsung-s24",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        url="/samsung-galaxy-s24-5g-amber-yellow-128-gb/p/itg?pid=SIZE128",
    )
    large = make_product(
        platform="Flipkart",
        product_key="samsung-s24",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)",
        price_value=55999.0,
        url="/samsung-galaxy-s24-5g-amber-yellow-256-gb/p/ith?pid=SIZE256",
    )

    results = aggregate_products([small, large])

    assert len(results) == 2
    for group in results:
        assert len(group["offers"]) == 1
        assert "128 GB" in group["title"] or "256 GB" in group["title"]


# --- 6. Exact duplicate offers are still removed --------------------------

def test_exact_duplicate_offers_are_still_removed(make_product):
    offer = make_product(
        platform="Amazon",
        product_key="samsung-galaxy-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        url="https://www.amazon.in/dp/B0DUPAMS24",
    )
    results = aggregate_products([offer, dict(offer)])

    (group,) = results
    assert len(group["offers"]) == 1


# --- 7. Same product + same store + same price, different valid URLs
#        remain separate offers (they are the same SKU, different listings)

def test_same_sku_different_valid_urls_stay_as_separate_offers(make_product):
    listing_a = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/ita?pid=LISTINGA",
    )
    listing_b = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itb?pid=LISTINGB",
    )

    results = aggregate_products([listing_a, listing_b])

    (group,) = results
    assert len(group["offers"]) == 2
    assert {o["url"] for o in group["offers"]} == {
        "/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/ita?pid=LISTINGA",
        "/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itb?pid=LISTINGB",
    }


# --- 8. Different stores for the exact same product stay grouped ---------

def test_same_exact_product_across_stores_stays_grouped(make_product):
    flipkart = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        price_display="\u20b949,999",
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itf?pid=FK128A",
    )
    amazon = make_product(
        platform="Amazon",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=50999.0,
        price_display="\u20b950,999",
        url="https://www.amazon.in/dp/B0AMBERRY128",
    )

    results = aggregate_products([flipkart, amazon])

    (group,) = results
    assert group["best_platform"] == "Flipkart"
    assert group["best_price"] == "\u20b949,999"
    assert {o["platform"] for o in group["offers"]} == {"Flipkart", "Amazon"}
    assert len({_sku_of(o) for o in group["offers"]}) == 1


# --- 9. Cheapest offer is selected correctly after dedup ------------------

def test_cheapest_offer_selected_after_dedup(make_product):
    dup_one = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=50999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/ita?pid=SKUFA&srno=s_1_1",
    )
    dup_two = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=50999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/ita?pid=SKUFA&srno=s_1_2",
    )
    cheap = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        price_display="\u20b949,999",
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itb?pid=SKUFB",
    )

    results = aggregate_products([dup_one, dup_two, cheap])

    (group,) = results
    assert len(group["offers"]) == 2
    assert group["best_price"] == "\u20b949,999"
    assert group["best_platform"] == "Flipkart"


# --- 10. Cheapest offer's View Deal URL is used for the card -------------

def test_cheapest_offer_url_used_for_card(make_product):
    pricier = make_product(
        platform="Amazon",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=54999.0,
        url="https://www.amazon.in/dp/B0EXPENSIVE",
    )
    cheapest = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        price_display="\u20b949,999",
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itc?pid=CHEAPEST",
    )

    results = aggregate_products([pricier, cheapest])

    (group,) = results
    assert group["best_url"] == cheapest["url"]
    assert "CHEAPEST" in group["best_url"]


# --- 11. Store filtering must not corrupt grouping ------------------------

def test_store_filtering_does_not_corrupt_grouping(make_product):
    amber_fk = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/ita?pid=AMK",
    )
    amber_amazon = make_product(
        platform="Amazon",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=50999.0,
        url="https://www.amazon.in/dp/B0AMBK",
    )
    onyx_amazon = make_product(
        platform="Amazon",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        price_value=51999.0,
        url="https://www.amazon.in/dp/B0ONYX",
    )

    results = aggregate_products([amber_fk, amber_amazon, onyx_amazon])
    assert len(results) == 2

    # Simulate the frontend's per-store filtering. Whatever the store filter,
    # every remaining offer in a card must describe the same single SKU.
    for store in ("Amazon", "Flipkart"):
        cards = [g for g in results if g["best_platform"] == store]
        for card in cards:
            filtered = [o for o in card["offers"] if o["platform"] == store]
            if not filtered and store == "Flipkart":
                continue
            assert len({_sku_of(o) for o in filtered}) == 1

    # Amber appears on both stores and must stay one card; Onyx stays its own.
    amber_cards = [g for g in results if "Amber Yellow" in g["title"]]
    onyx_cards = [g for g in results if "Onyx Black" in g["title"]]
    assert len(amber_cards) == 1
    assert len(onyx_cards) == 1
    assert {o["platform"] for o in amber_cards[0]["offers"]} == {"Flipkart", "Amazon"}
    assert {o["platform"] for o in onyx_cards[0]["offers"]} == {"Amazon"}


# --- 12. Missing-URL fallback still works ---------------------------------

def test_missing_url_fallback_still_works(make_product):
    first = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
    )
    first["url"] = None
    duplicate = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
    )
    duplicate["url"] = None
    other_sku = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        price_value=49999.0,
    )
    other_sku["url"] = None

    results = aggregate_products([first, duplicate, other_sku])

    assert len(results) == 2
    assert sum(len(g["offers"]) for g in results) == 2
    assert all(len(g["offers"]) == 1 for g in results)


# --- Cross-cutting invariant: every card is a single SKU ------------------

def test_every_offer_in_a_card_resolves_to_one_sku(make_product):
    offers = [
        make_product(
            platform="Flipkart",
            product_key="s24-256gb",
            title="Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)",
            price_value=55999.0,
            url="/samsung-galaxy-s24-256-gb-exynos/p/itc?pid=AAA",
        ),
        make_product(
            platform="Flipkart",
            product_key="s24-256gb",
            title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)",
            price_value=55999.0,
            url="/samsung-galaxy-s24-256-gb-snap/p/itd?pid=BBB",
        ),
        make_product(
            platform="Flipkart",
            product_key="z11",
            title="Z11 5G (Celestial Blue, 8GB RAM, 128GB Storage)",
            price_value=39999.0,
            url="/z11-5g-celestial-blue/p/ite?pid=ZZZ",
        ),
    ]

    results = aggregate_products(offers)

    for group in results:
        skus = {_sku_of(o) for o in group["offers"]}
        assert len(skus) == 1, f"card {group['title']!r} mixes multiple SKUs: {skus}"