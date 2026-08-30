from app.aggregator.aggregator import aggregate_products


def test_exact_duplicate_offer_is_kept_once(make_product):
    offer = make_product(
        platform="Flipkart",
        title="Samsung Galaxy S24 5G 256GB",
        product_key="samsung-galaxy-s24-256gb",
        price_value=55999.0,
        price_display="\u20b955,999",
        url="/samsung-galaxy-s24-5g/p/itm1?pid=MOBX",
    )
    products = [offer, dict(offer)]

    results = aggregate_products(products)

    (group,) = results
    assert len(group["offers"]) == 1
    assert group["best_price"] == "\u20b955,999"


def test_flipkart_tracking_query_duplicates_are_deduplicated(make_product):
    """
    The same Flipkart listing can recur with different personalisation
    params (qid, iid, srno, ssid). Only the product path+pid is meaningful.
    """
    first = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        price_value=55999.0,
        price_display="\u20b955,999",
        url="/samsung-galaxy-s24-5g/p/itm1?pid=MOBX&qid=111&iid=aaa.MOBX.SEARCH&srno=s_1_1",
    )
    second = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        price_value=55999.0,
        price_display="\u20b955,999",
        url="/samsung-galaxy-s24-5g/p/itm1?pid=MOBX&qid=222&iid=bbb.MOBX.SEARCH&srno=s_1_2",
    )

    results = aggregate_products([first, second])

    (group,) = results
    assert len(group["offers"]) == 1
    assert "pid=MOBX" in group["offers"][0]["url"]


def test_same_store_same_price_different_url_is_preserved(make_product):
    """
    Distinct products (colour/chipset variants) share a price but must NOT be
    collapsed - they have different URLs (product ids) and different SKUs, so
    each becomes its own product card.
    """
    amber = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        title="Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)",
        price_value=55999.0,
        url="/samsung-galaxy-s24-exynos-5g-amber-yellow-256-gb/p/itmA?pid=MOBA",
    )
    violet = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        title="Samsung Galaxy S24 5G Snapdragon (Cobalt Violet, 256 GB)",
        price_value=55999.0,
        url="/samsung-galaxy-s24-5g-snapdragon-cobalt-violet-256-gb/p/itmB?pid=MOBB",
    )

    results = aggregate_products([amber, violet])

    assert len(results) == 2
    assert {o["title"] for g in results for o in g["offers"]} == {
        "Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)",
        "Samsung Galaxy S24 5G Snapdragon (Cobalt Violet, 256 GB)",
    }
    assert all(len(g["offers"]) == 1 for g in results)


def test_same_store_different_prices_are_preserved(make_product):
    cheaper = make_product(
        platform="Amazon",
        product_key="samsung-galaxy-s24-8gb",
        title="Galaxy S24 (Onyx Black, 8GB)",
        price_value=58799.0,
        price_display="\u20b958,799",
        url="https://www.amazon.in/dp/B0CS69QQTG",
    )
    dearer = make_product(
        platform="Amazon",
        product_key="samsung-galaxy-s24-8gb",
        title="Galaxy S24 (Amber Yellow, 8GB)",
        price_value=69999.0,
        price_display="\u20b969,999",
        url="https://www.amazon.in/dp/B0CS6M6JLF",
    )

    results = aggregate_products([cheaper, dearer])

    assert len(results) == 2
    assert {g["best_price"] for g in results} == {"\u20b958,799", "\u20b969,999"}
    assert {g["best_platform"] for g in results} == {"Amazon"}


def test_different_stores_with_same_price_are_preserved(make_product):
    flipkart = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        price_value=55999.0,
        url="/samsung-galaxy-s24-5g/p/itm1?pid=MOBX",
    )
    amazon = make_product(
        platform="Amazon",
        product_key="samsung-galaxy-s24-256gb",
        price_value=55999.0,
        url="https://www.amazon.in/dp/B0H297XH3K",
    )

    results = aggregate_products([flipkart, amazon])

    (group,) = results
    assert len(group["offers"]) == 2
    assert {o["platform"] for o in group["offers"]} == {"Flipkart", "Amazon"}


def test_cheapest_offer_still_identified_after_dedup(make_product):
    dup_one = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        price_value=60000.0,
        price_display="\u20b960,000",
        url="/samsung-galaxy-s24-5g/p/itm1?pid=MOBX&srno=s_1_1",
    )
    dup_two = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        price_value=60000.0,
        price_display="\u20b960,000",
        url="/samsung-galaxy-s24-5g/p/itm1?pid=MOBX&srno=s_1_2",
    )
    cheap = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        price_value=55999.0,
        price_display="\u20b955,999",
        url="/samsung-galaxy-s24-5g/p/itm2?pid=MOBY",
    )

    results = aggregate_products([dup_one, dup_two, cheap])

    (group,) = results
    assert len(group["offers"]) == 2
    assert group["best_price"] == "\u20b955,999"
    assert group["best_platform"] == "Flipkart"
    assert "MOBY" in group["best_url"]


def test_view_deal_url_stays_with_retained_offer(make_product):
    first = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        price_value=55999.0,
        price_display="\u20b955,999",
        url="/keep-me/p/itm1?pid=KEEP&srno=s_1_1",
    )
    duplicate = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        price_value=55999.0,
        price_display="\u20b955,999",
        url="/keep-me/p/itm1?pid=KEEP&srno=s_1_2",
    )

    results = aggregate_products([first, duplicate])

    (group,) = results
    (offer,) = group["offers"]
    assert "pid=KEEP&srno=s_1_1" in offer["url"]
    assert group["best_url"] == offer["url"]


def test_amazon_sponsored_click_url_dedups_with_plain_dp_url(make_product):
    sponsored = make_product(
        platform="Amazon",
        product_key="turbo-5-8gb",
        price_value=41999.0,
        price_display="\u20b941,999",
        url="https://www.amazon.in/sspa/click?ie=UTF8&url=%2FAsphalt-5G%2Fdp%2FB0H297XH3K%2Fref%3Dsr_1_3%3Fkeywords%3Dsamsung%26qid%3D1787815584",
    )
    plain = make_product(
        platform="Amazon",
        product_key="turbo-5-8gb",
        price_value=41999.0,
        price_display="\u20b941,999",
        url="https://www.amazon.in/dp/B0H297XH3K",
    )

    results = aggregate_products([sponsored, plain])

    (group,) = results
    assert len(group["offers"]) == 1


def test_missing_url_fallback_identity_uses_available_fields(make_product):
    """
    Identical URL-less records of the *same* SKU deduplicate; a genuinely
    different SKU (S24 FE) becomes its own product card instead of being
    merged into the S24 card.
    """
    first_no_url = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        title="Samsung Galaxy S24 256GB",
        price_value=55999.0,
    )
    first_no_url["url"] = None
    second_no_url = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        title="Samsung Galaxy S24 256GB",
        price_value=55999.0,
    )
    second_no_url["url"] = None
    different_variant_no_url = make_product(
        platform="Flipkart",
        product_key="samsung-galaxy-s24-256gb",
        title="Samsung Galaxy S24 FE 256GB",
        price_value=55999.0,
    )
    different_variant_no_url["url"] = None

    results = aggregate_products([first_no_url, second_no_url, different_variant_no_url])

    assert len(results) == 2
    by_title = {g["title"]: g for g in results}
    assert set(by_title) == {
        "Samsung Galaxy S24 256GB",
        "Samsung Galaxy S24 FE 256GB",
    }
    assert len(by_title["Samsung Galaxy S24 256GB"]["offers"]) == 1
    assert len(by_title["Samsung Galaxy S24 FE 256GB"]["offers"]) == 1


def test_s24_exynos_distinct_skus_same_price_survive_with_identifiers(make_product):
    """
    End-to-end shape for the reported S24 Exynos card: six Flipkart offers
    at the same price with different IDs. They are genuinely different SKUs
    (colour/chipset shown in the title, distinct pid in the URL), so each
    must become its OWN product card — never merged into one card — keeping
    its own title, price and View Deal URL.
    """
    offers = [
        make_product(
            platform="Flipkart",
            product_key="samsung-s24-256gb",
            title="Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)",
            price_value=55999.0,
            price_display="\u20b955,999",
            url="/samsung-galaxy-s24-exynos-5g-amber-yellow-256-gb/p/itm7eaf?pid=MOBGX2F3TYAVSQJC",
        ),
        make_product(
            platform="Flipkart",
            product_key="samsung-s24-256gb",
            title="Samsung Galaxy S24 5G Snapdragon (Cobalt Violet, 256 GB)",
            price_value=55999.0,
            price_display="\u20b955,999",
            url="/samsung-galaxy-s24-5g-snapdragon-cobalt-violet-256-gb/p/itm0e455?pid=MOBHDVFKKYGS2K9T",
        ),
        make_product(
            platform="Flipkart",
            product_key="samsung-s24-256gb",
            title="Samsung Galaxy S24 5G Snapdragon (Onyx Black, 256 GB)",
            price_value=55999.0,
            price_display="\u20b955,999",
            url="/samsung-galaxy-s24-5g-snapdragon-onyx-black-256-gb/p/itm0eb31?pid=MOBHDVFKVGGGHBDX",
        ),
        make_product(
            platform="Flipkart",
            product_key="samsung-s24-256gb",
            title="Samsung Galaxy S24 5G Snapdragon (Marble Gray, 256 GB)",
            price_value=55999.0,
            price_display="\u20b955,999",
            url="/samsung-galaxy-s24-5g-snapdragon-marble-gray-256-gb/p/itmc60e0?pid=MOBHDVFKAWDVHJTU",
        ),
        make_product(
            platform="Flipkart",
            product_key="samsung-s24-256gb",
            title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)",
            price_value=55999.0,
            price_display="\u20b955,999",
            url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-256-gb/p/itm170d9?pid=MOBHDVFKDNDVPYMK",
        ),
        make_product(
            platform="Flipkart",
            product_key="samsung-s24-256gb",
            title="Samsung Galaxy S24 Exynos 5G (Marble Gray, 256 GB)",
            price_value=75999.0,
            price_display="\u20b975,999",
            url="/samsung-galaxy-s24-exynos-5g-marble-gray-256-gb/p/itm9cd4c?pid=MOBH5TKXJBNXDGRE",
        ),
    ]

    results = aggregate_products(offers)

    assert len(results) == 6, "each distinct SKU must be its own product card"
    assert len({g["title"] for g in results}) == 6
    assert all(len(g["offers"]) == 1 for g in results)
    assert all(g["offers"][0]["url"] for g in results), \
        "every SKU keeps its View Deal URL"
    cheap = [g for g in results if g["best_price"] == "\u20b955,999"]
    assert len(cheap) == 5
    assert all(g["best_platform"] == "Flipkart" for g in results)
    assert all("pid=" in g["offers"][0]["url"] for g in results)


def test_duplicate_record_plus_distinct_sku_at_same_price(make_product):
    """
    A Windows-fallback style duplicate (same listing recurs with different
    tracking params) must collapse into a single offer, while a genuinely
    different SKU at the same store + same price must get its own card.
    """
    dup_one = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        price_display="\u20b949,999",
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itmd4baa?pid=MOBHDVFKSZNEZGXW&srno=s_1_1",
    )
    dup_two = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        price_value=49999.0,
        price_display="\u20b949,999",
        url="/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itmd4baa?pid=MOBHDVFKSZNEZGXW&srno=s_1_2",
    )
    other_sku = make_product(
        platform="Flipkart",
        product_key="samsung-s24-128gb",
        title="Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        price_value=49999.0,
        price_display="\u20b949,999",
        url="/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/itm3469a?pid=MOBHDVFKSSHPUYHB&srno=s_1_3",
    )

    results = aggregate_products([dup_one, dup_two, other_sku])

    assert len(results) == 2
    amber_card = next(g for g in results if "Amber Yellow" in g["title"])
    onyx_card = next(g for g in results if "Onyx Black" in g["title"])
    assert len(amber_card["offers"]) == 1
    assert len(onyx_card["offers"]) == 1
    assert "MOBHDVFKSZNEZGXW" in amber_card["offers"][0]["url"]
    assert "MOBHDVFKSSHPUYHB" in onyx_card["offers"][0]["url"]