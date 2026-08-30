from app.utils.category import detect_category


def test_fashion_category_detection():
    assert detect_category("nike running shoes") == "Fashion"
    assert detect_category("cotton shirt for men") == "Fashion"
    assert detect_category("leather bag") == "Fashion"
    assert detect_category("denim jeans") == "Fashion"
    assert detect_category("summer fashion dress") == "Fashion"


def test_electronics_category_detection():
    assert detect_category("laptop under 50000") == "Electronics"
    assert detect_category("iphone 15") == "Electronics"
    assert detect_category("55 inch tv") == "Electronics"
    assert detect_category("electronics accessories") == "Electronics"


def test_beauty_category_detection():
    assert detect_category("vitamin c serum") == "Beauty"
    assert detect_category("moisturizing cream") == "Beauty"
    assert detect_category("skincare routine") == "Beauty"
    assert detect_category("beauty products") == "Beauty"


def test_general_category_is_fallback():
    assert detect_category("random query xyz") == "General"
    assert detect_category("") == "General"
    assert detect_category("12345") == "General"


def test_category_detection_is_case_insensitive():
    assert detect_category("LAPTOP") == "Electronics"
    assert detect_category("Shoes") == "Fashion"
    assert detect_category("SERUM") == "Beauty"
