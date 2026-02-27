import re


# -----------------------------
# CLEAN TEXT
# -----------------------------
def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip().lower()


# -----------------------------
# BRAND EXTRACTION
# -----------------------------
def extract_brand(title: str):
    title = title.lower()

    brands = [
        "apple",
        "samsung",
        "oneplus",
        "realme",
        "xiaomi",
        "redmi",
        "iqoo",
        "vivo",
        "oppo",
        "nothing",
        "motorola",
        "google",
        "pixel"
    ]

    for brand in brands:
        if brand in title:
            return brand

    return None


# -----------------------------
# MODEL NUMBER EXTRACTION
# -----------------------------
def extract_model_number(title: str):
    """
    Extract models like:
    iPhone 15
    iPhone 14
    S24
    S23
    """

    title = title.lower()

    # iPhone models
    match = re.search(r'iphone\s?(\d{1,2})', title)
    if match:
        return "iphone" + match.group(1)

    # Samsung Galaxy S models
    match = re.search(r'\bs(\d{1,2})\b', title)
    if match:
        return "s" + match.group(1)

    return None


# -----------------------------
# STORAGE EXTRACTION
# -----------------------------
def extract_storage(title: str):
    """
    Extract storage like:
    128GB
    256GB
    512GB
    1TB
    """

    match = re.search(r'(\d+)\s?(gb|tb)', title.lower())

    if match:
        return match.group(1) + match.group(2)

    return None


# -----------------------------
# MAIN NORMALIZER
# -----------------------------
def normalize_product(title: str):
    """
    Returns structured product info
    """

    title_clean = clean_text(title)

    return {
        "brand": extract_brand(title_clean),
        "model": extract_model_number(title_clean),
        "storage": extract_storage(title_clean)
    }