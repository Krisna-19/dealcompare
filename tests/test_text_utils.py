from app.utils.text_utils import (
    extract_model_number,
    extract_product_info,
    extract_storage,
    extract_variant_attributes,
    generate_product_key,
    normalize_text,
)


def test_iphone_key_format():
    assert generate_product_key("Apple iPhone 15 (128 GB) - Black") == "apple-15-128gb"


def test_iphone_storage_is_not_mistaken_for_model():
    brand, model, storage = extract_product_info("iphone 15 128gb")
    assert (brand, model, storage) == ("apple", "15", "128gb")


def test_samsung_key_with_alphanumeric_model():
    assert (
        generate_product_key("SAMSUNG Galaxy S24 Ultra 5G 256GB")
        == "samsung-s24-ultra-256gb"
    )


def test_oneplus_key():
    assert generate_product_key("OnePlus 12 256GB SuperVOOC") == "oneplus-12-256gb"


def test_pixel_key_maps_to_google():
    assert generate_product_key("Google Pixel 8 Pro 128GB") == "google-8-pro-128gb"


def test_s24_and_s24_fe_keys_differ():
    assert (
        generate_product_key("Samsung Galaxy S24 5G 256GB")
        != generate_product_key("Samsung Galaxy S24 FE 5G 256GB")
    )


def test_trailing_brand_mention_does_not_hide_the_model():
    """
    Amazon-style marketing text re-mentions the brand after the model
    (e.g. "... for Galaxy Processor", "... | Galaxy AI"). That trailing
    mention must NOT suppress the model number, otherwise an S25 card
    would leak into an S24 search and S24 vs S24 FE could re-merge.
    """
    brand, model, storage = extract_product_info(
        "Galaxy S25 5G (Silver Shadow, 12GB RAM, 128GB Storage) "
        "| Snapdragon 8 Elite for Galaxy Processor"
    )
    assert (brand, model, storage) == ("samsung", "s25", "128gb")

    brand, model, storage = extract_product_info(
        "Samsung Galaxy S24 5G ... | Galaxy AI"
    )
    assert brand == "samsung" and model == "s24"
    assert model != extract_product_info("Samsung Galaxy S24 FE 5G ... | Galaxy AI")[1]
    assert (
        generate_product_key("Samsung Galaxy S24 256GB | Galaxy AI")
        != generate_product_key("Samsung Galaxy S24 FE 256GB | Galaxy AI")
    )


def test_brand_alias_variants_produce_identical_keys():
    assert (
        generate_product_key("Apple iPhone 15 128GB")
        == generate_product_key("iPhone 15 128 GB")
    )


def test_unbranded_title_gets_fallback_key():
    assert (
        generate_product_key("Men Regular Fit Cotton T-Shirt")
        == "men-regular-fit-cotton-t-shirt"
    )


def test_unbranded_title_with_number_noise_still_groups_via_fallback():
    assert (
        generate_product_key("Pack of 2 Cotton T-Shirts (Multicolor)")
        == "pack-of-2-cotton-t-shirts"
    )


def test_blank_title_returns_none():
    assert generate_product_key("   ") is None


# --- normalize_text --------------------------------------------------------

def test_normalize_text_lowercases():
    assert normalize_text("Hello World") == "hello world"


def test_normalize_text_strips_special_characters():
    assert normalize_text("iPhone 15 (128 GB) - Black") == "iphone 15 128 gb black"


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  too   many   spaces  ") == "too many spaces"


def test_normalize_text_empty_string():
    assert normalize_text("") == ""


def test_product_type_isolates_material_noun():
    # unbranded titles: product type differentiates materially different items
    assert extract_product_info("Men Casual Black Genuine Leather Wallet")[0] is None
    assert extract_variant_attributes("Men Casual Black Genuine Leather Wallet")["product_type"] == "wallet"
    assert extract_variant_attributes("Men Casual Black Genuine Leather Card Holder")["product_type"] == "card holder"
    assert extract_variant_attributes("Women Black Genuine Leather Handbag")["product_type"] == "handbag"
    assert extract_variant_attributes("Women Black Genuine Leather Trolley Bag")["product_type"] == "trolley"
    assert extract_variant_attributes("Teakwood Genuine Leather Biker Jacket")["product_type"] == "jacket"


def test_product_type_not_set_for_branded_electronics():
    # branded electronics must not gain a product type (keeps S24 grouping stable)
    assert extract_variant_attributes("Samsung Galaxy S24 5G Smartphone")["product_type"] is None


# --- extract_model_number --------------------------------------------------

def test_extract_model_number_returns_first_number():
    assert extract_model_number("iphone 15 128gb") == "15"


def test_extract_model_number_returns_none_for_no_numbers():
    assert extract_model_number("no numbers here") is None


def test_extract_model_number_handles_single_digit():
    assert extract_model_number("model 9 pro") == "9"


def test_extract_model_number_handles_two_digit():
    assert extract_model_number("iphone 15") == "15"


def test_extract_model_number_handles_three_digit():
    assert extract_model_number("model 123 edition") == "123"


# --- extract_storage -------------------------------------------------------

def test_extract_storage_returns_gb_value():
    assert extract_storage("128gb") == "128gb"


def test_extract_storage_handles_space_before_unit():
    assert extract_storage("256 gb") == "256gb"


def test_extract_storage_returns_tb_value():
    assert extract_storage("1tb ssd") == "1tb"


def test_extract_storage_returns_none_when_absent():
    assert extract_storage("no storage here") is None


def test_extract_storage_case_insensitive():
    assert extract_storage("512GB") == "512gb"


# --- pack_count / size_cm / marketplace-prefix attributes ------------------

def test_pack_count_extracts_quantity():
    attrs = extract_variant_attributes("Men Casual Cotton Socks (Pack of 6)")
    assert attrs["pack_count"] == 6


def test_pack_count_distinguishes_6_from_8():
    assert extract_variant_attributes("Men Casual Cotton Socks (Pack of 6)")[
        "pack_count"
    ] == 6
    assert extract_variant_attributes("Men Casual Cotton Socks (Pack of 8)")[
        "pack_count"
    ] == 8


def test_pack_count_accepts_set_and_combo_phrasing():
    assert extract_variant_attributes("Set of 3 Stainless Steel Spoons")["pack_count"] == 3
    assert extract_variant_attributes("Combo of 2 Mugs")["pack_count"] == 2


def test_pack_count_is_none_when_single_unit():
    attrs = extract_variant_attributes("Men Casual Cotton Socks")
    assert attrs["pack_count"] is None


def test_physical_size_extracts_cm():
    attrs = extract_variant_attributes("Women Cabin Size Trolley Bag 55 cm")
    assert attrs["size_cm"] == "55cm"


def test_physical_size_distinguishes_55_from_65():
    assert extract_variant_attributes("Women Cabin Size Trolley Bag 55 cm")[
        "size_cm"
    ] == "55cm"
    assert extract_variant_attributes("Women Cabin Size Trolley Bag 65 cm")[
        "size_cm"
    ] == "65cm"


def test_physical_size_tracks_inch_unit():
    assert extract_variant_attributes("Monitor 24 inches")["size_cm"] == "24in"
    # Android 'inch' is in the electronics stop-words, but a display-size-less
    # product still reports its physical unit when present.
    assert extract_variant_attributes("27 inch Display")["size_cm"] == "27in"


def test_physical_size_is_none_without_a_unit():
    # A shoe "Size 8" carries no physical unit, so it must NOT be mistaken for
    # an explicit cm/inch size (which would wrongly split shoe sizes).
    assert extract_variant_attributes("Nike Men Air Max 270 Running Shoes Size 8")[
        "size_cm"
    ] is None


def test_marketplace_prefix_does_not_pollute_model():
    # Amazon-style "MC" retailer designation must not change the model key.
    assert (
        extract_variant_attributes("Samsung Galaxy S24 5G (Marble Gray, 128 GB)")["model"]
        == extract_variant_attributes(
            "Samsung Galaxy S24 MC 5G (Marble Gray, 128 GB)"
        )["model"]
        == "s24"
    )
