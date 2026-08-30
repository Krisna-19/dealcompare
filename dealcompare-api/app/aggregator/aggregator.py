import re
from collections import defaultdict


# -----------------------------
# NORMALIZE TEXT
# -----------------------------
def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# -----------------------------
# EXTRACT MODEL NUMBER
# -----------------------------
def extract_model_number(text: str):
    match = re.search(r"\b\d{1,2}\b", text)
    return match.group() if match else ""


# -----------------------------
# EXTRACT STORAGE
# -----------------------------
def extract_storage(text: str):
    match = re.search(r"(\d{2,4})\s?gb", text.lower())
    return match.group(1) if match else ""


# -----------------------------
# GENERATE GROUP KEY
# -----------------------------
def generate_group_key(title: str):

    title_norm = normalize(title)

    model = extract_model_number(title_norm)
    storage = extract_storage(title_norm)

    key_parts = []

    # detect common brands
    brands = ["iphone", "samsung", "oneplus", "xiaomi", "realme", "oppo"]

    for brand in brands:
        if brand in title_norm:
            key_parts.append(brand)
            break

    if model:
        key_parts.append(model)

    if storage:
        key_parts.append(storage)

    if not key_parts:
        words = title_norm.split()[:4]
        key_parts = words

    return "-".join(key_parts)


# -----------------------------
# AGGREGATE PRODUCTS
# -----------------------------
def aggregate_products(products):

    grouped = {}

    for product in products:

        key = product.get("product_key")

        if not key:
            continue

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(product)

    results = []

    for key, items in grouped.items():

        best = min(items, key=lambda x: x["price_value"] if x["price_value"] else float("inf"))

        results.append({
            "title": best["title"],
            "best_price": best["price_display"],
            "best_platform": best["platform"],
            "best_url": best["url"],
            "offers": items
        })

    return results