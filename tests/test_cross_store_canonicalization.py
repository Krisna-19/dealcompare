"""
Cross-store canonicalization tests.

Different retailers use different title wording for the same physical SKU:

  Amazon: "Galaxy S24 Snapdragon 8 Gen 3 5G (Onyx Black, 128 GB) (8 GB RAM)"
  Flipkart: "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)"

These describe the SAME canonical SKU (brand + model + chipset + RAM +
storage + colour) and must land in ONE product card whose offers[] contains
both stores.  Genuinely different products must stay separate.
"""
from app.aggregator.aggregator import aggregate_products


def _p(title, price, platform, url, key="s24"):
    return {
        "title": title,
        "product_key": key,
        "platform": platform,
        "price_value": price,
        "price_display": f"\u20b9{int(price):,}",
        "url": url,
        "image": "",
    }


# --- SAME canonical SKU across stores -------------------------------------

def test_amazon_and_flipkart_same_sku_merge_into_one_card():
    amazon = _p(
        "Galaxy S24 Snapdragon 8 Gen 3 5G (Onyx Black, 128 GB) (8 GB RAM)",
        54499.0, "Amazon",
        "https://www.amazon.in/dp/B0ONYX128",
    )
    flipkart = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        49999.0, "Flipkart",
        "/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/itx?pid=ONYXFK",
    )

    results = aggregate_products([amazon, flipkart])

    assert len(results) == 1, "same SKU across stores must be ONE card"
    (group,) = results
    assert {o["platform"] for o in group["offers"]} == {"Amazon", "Flipkart"}
    assert group["best_platform"] == "Flipkart"
    assert group["best_price"] == "\u20b949,999"


def test_ram_stated_on_one_side_only_is_not_a_split():
    """One retailer states 'GB RAM', the other omits it -> still one SKU."""
    with_ram = _p(
        "Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
        54499.0, "Amazon", "https://www.amazon.in/dp/B0RAMLESSUZ",
    )
    no_ram = _p(
        "Samsung Galaxy S24 5G (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/samsung-galaxy-s24-onyx-black-128-gb/p/itx?pid=NORAM",
    )

    results = aggregate_products([with_ram, no_ram])

    assert len(results) == 1
    assert len(results[0]["offers"]) == 2


def test_chipset_stated_on_one_side_only_is_not_a_split():
    """Amazon often omits the chipset; Flipkart states it -> still one SKU."""
    no_chipset = _p(
        "Galaxy S24 5G Smartphone (Onyx Black, 8GB, 128GB Storage)",
        54499.0, "Amazon", "https://www.amazon.in/dp/B0NOCHIP",
    )
    with_chipset = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/itx?pid=CHIP",
    )

    results = aggregate_products([no_chipset, with_chipset])

    assert len(results) == 1
    assert {o["platform"] for o in results[0]["offers"]} == {"Amazon", "Flipkart"}


def test_different_stores_different_prices_kept_as_two_offers():
    amazon = _p(
        "Galaxy S24 Snapdragon 8 Gen 3 5G (Onyx Black, 128 GB) (8 GB RAM)",
        54499.0, "Amazon", "https://www.amazon.in/dp/B0A545",
    )
    flipkart = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/itx?pid=FK545",
    )

    (group,) = aggregate_products([amazon, flipkart])

    assert len(group["offers"]) == 2
    assert {o["price_value"] for o in group["offers"]} == {54499.0, 49999.0}
    assert group["best_platform"] == "Flipkart"
    assert group["best_price"] == "\u20b949,999"


# --- Different SKUs must stay separate --------------------------------------

def test_storage_difference_splits_cards():
    small = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/s24-128/p/itx?pid=A",
    )
    large = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 256 GB)",
        55999.0, "Flipkart", "/s24-256/p/itx?pid=B",
    )

    assert len(aggregate_products([small, large])) == 2


def test_chipset_difference_splits_cards():
    snapdragon = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/s24-snap/p/itx?pid=A",
    )
    exynos = _p(
        "Samsung Galaxy S24 Exynos 5G (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/s24-exynos/p/itx?pid=B",
    )

    assert len(aggregate_products([snapdragon, exynos])) == 2


def test_explicit_ram_difference_splits_cards():
    ram8 = _p(
        "Samsung Galaxy S24 5G (Onyx Black, 128 GB) (8 GB RAM)",
        49999.0, "Flipkart", "/s24-8gb/p/itx?pid=A",
    )
    ram12 = _p(
        "Samsung Galaxy S24 5G (Onyx Black, 128 GB) (12 GB RAM)",
        51999.0, "Flipkart", "/s24-12gb/p/itx?pid=B",
    )

    assert len(aggregate_products([ram8, ram12])) == 2


def test_color_difference_splits_cards():
    onyx = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/s24-onyx/p/itx?pid=A",
    )
    amber = _p(
        "Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 128 GB)",
        49999.0, "Flipkart", "/s24-amber/p/itx?pid=B",
    )

    assert len(aggregate_products([onyx, amber])) == 2


def test_model_generation_difference_splits_cards():
    s24 = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/s24/p/itx?pid=A",
    )
    s25 = _p(
        "Galaxy S25 5G Snapdragon (Onyx Black, 128 GB)",
        59999.0, "Amazon", "https://www.amazon.in/dp/B0S25ONYX",
    )

    assert len(aggregate_products([s24, s25])) == 2


# --- Canonical shape + deduplication ----------------------------------------

def test_same_store_same_id_same_sku_is_one_offer():
    """Same store + same product id + same canonical SKU -> ONE offer."""
    amazon_a = _p(
        "Galaxy S24 Snapdragon 8 Gen 3 5G (Onyx Black, 128 GB) (8 GB RAM)",
        54499.0, "Amazon", "https://www.amazon.in/dp/B00NYS24X1",
    )
    amazon_b = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        54499.0, "Amazon", "https://www.amazon.in/sspa/click?url=%2Fdp%2FB00NYS24X1",
    )

    (group,) = aggregate_products([amazon_a, amazon_b])
    assert len(group["offers"]) == 1


def test_merged_card_keeps_both_urls_and_cheapest_wins():
    amazon = _p(
        "Galaxy S24 Snapdragon 8 Gen 3 5G (Onyx Black, 128 GB) (8 GB RAM)",
        54499.0, "Amazon", "https://www.amazon.in/dp/B0MERGED",
    )
    flipkart = _p(
        "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
        49999.0, "Flipkart", "/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/ity?pid=FKMERGE",
    )

    (group,) = aggregate_products([amazon, flipkart])
    assert group["best_url"] == flipkart["url"]
    assert {o["url"] for o in group["offers"]} == {amazon["url"], flipkart["url"]}