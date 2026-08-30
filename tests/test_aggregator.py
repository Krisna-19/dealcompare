from app.aggregator.aggregator import aggregate_products


def test_zero_price_placeholders_are_dropped(make_product):
    products = [
        make_product(platform="Amazon", price_value=79999.0, price_display="\u20b979,999"),
        make_product(platform="FakeMart", price_value=0, price_display="Check price"),
        make_product(platform="NoPrice", price_value=None),
    ]

    results = aggregate_products(products)

    assert len(results) == 1
    group = results[0]
    assert {offer["platform"] for offer in group["offers"]} == {"Amazon"}
    assert group["best_platform"] == "Amazon"
    assert group["best_price"] == "\u20b979,999"


def test_negative_price_entries_are_dropped(make_product):
    products = [
        make_product(platform="Amazon", price_value=79999.0),
        make_product(platform="BadData", price_value=-500.0, price_display="\u2212\u20b9500"),
    ]

    results = aggregate_products(products)

    assert len(results) == 1
    assert {offer["platform"] for offer in results[0]["offers"]} == {"Amazon"}


def test_all_placeholder_input_yields_honest_empty_result(make_product):
    products = [
        make_product(platform="StubA", price_value=0),
        make_product(platform="StubB", price_value=None),
    ]

    assert aggregate_products(products) == []


def test_cheapest_real_offer_wins_with_matching_url(make_product):
    cheap = make_product(
        platform="Flipkart",
        title="Apple iPhone 15 (128 GB) - Black",
        product_key="apple-iphone-15-128gb",
        price_value=78999.0,
        price_display="\u20b978,999",
        url="https://www.flipkart.com/iphone15",
    )
    dear = make_product(
        platform="Amazon",
        title="Apple iPhone 15 (128 GB) - Black",
        product_key="apple-iphone-15-128gb",
        price_value=81999.0,
        price_display="\u20b981,999",
        url="https://www.amazon.in/dp/A",
    )

    results = aggregate_products([dear, cheap])

    group = results[0]
    assert group["best_platform"] == "Flipkart"
    assert group["best_price"] == "\u20b978,999"
    assert group["best_url"] == "https://www.flipkart.com/iphone15"
    assert len(group["offers"]) == 2


def test_best_offer_is_minimum_price_regardless_of_input_order(make_product):
    """
    Contract: best_* fields must reference the cheapest valid offer.
    (The offers list itself preserves input order by design.)
    """
    products = [
        make_product(platform="Amazon", price_value=81999.0,
                     price_display="\u20b981,999", url="https://www.amazon.in/dp/A"),
        make_product(platform="Flipkart", price_value=78999.0,
                     price_display="\u20b978,999", url="https://www.flipkart.com/p/fk"),
        make_product(platform="Croma", price_value=80500.0,
                     price_display="\u20b980,500", url="https://www.croma.com/p/cr"),
    ]

    results = aggregate_products(products)

    group = results[0]
    assert group["best_price"] == "\u20b978,999"
    assert group["best_platform"] == "Flipkart"
    assert group["best_url"] == "https://www.flipkart.com/p/fk"
    assert {o["price_value"] for o in group["offers"]} == {81999.0, 78999.0, 80500.0}


def test_distinct_product_keys_produce_separate_groups(make_product):
    iphone = make_product(product_key="apple-iphone-15-128gb", price_value=79999.0)
    samsung = make_product(
        platform="Amazon",
        title="Samsung Galaxy S24 5G 256GB",
        product_key="samsung-galaxy-s24-256gb",
        price_value=64999.0,
        price_display="\u20b964,999",
    )

    results = aggregate_products([iphone, samsung])

    assert len(results) == 2
    by_title = {g["title"]: g for g in results}
    assert set(by_title) == {
        "Apple iPhone 15 (128 GB) - Black",
        "Samsung Galaxy S24 5G 256GB",
    }
    assert by_title["Apple iPhone 15 (128 GB) - Black"]["best_price"] == "\u20b979,999"
    assert by_title["Samsung Galaxy S24 5G 256GB"]["best_price"] == "\u20b964,999"


def test_group_contract_fields_are_complete(make_product):
    results = aggregate_products([make_product()])

    (group,) = results
    assert set(group.keys()) == {"title", "best_price", "best_platform", "best_url", "offers"}
    (offer,) = group["offers"]
    assert set(offer.keys()) >= {
        "title", "product_key", "platform", "price_value", "price_display", "url",
    }


def test_empty_input_returns_empty_list():
    assert aggregate_products([]) == []


def test_product_without_product_key_is_skipped(make_product):
    no_key = make_product(product_key=None, price_value=5000.0)
    no_key_str = make_product(product_key="", price_value=3000.0)
    valid = make_product(product_key="valid-key", price_value=4000.0)

    results = aggregate_products([no_key, no_key_str, valid])

    assert len(results) == 1
    assert results[0]["best_platform"] == "Amazon"


def test_single_product_forms_valid_group(make_product):
    results = aggregate_products([make_product(price_value=12345.0, price_display="\u20b912,345")])

    assert len(results) == 1
    group = results[0]
    assert group["best_price"] == "\u20b912,345"
    assert group["best_platform"] == "Amazon"
    assert len(group["offers"]) == 1


def test_product_key_must_be_non_empty_string(make_product):
    """Falsy product_key (0, False) should also be skipped."""
    zero_key = make_product(product_key=0, price_value=5000.0)
    valid = make_product(product_key="real-key", price_value=4000.0)

    results = aggregate_products([zero_key, valid])

    assert len(results) == 1
