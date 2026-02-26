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

    # build strict grouping key
    key_parts = []

    if "iphone" in title_norm:
        key_parts.append("iphone")

    if model:
        key_parts.append(model)

    if storage:
        key_parts.append(storage)

    if not key_parts:
        # fallback to first 3 words
        words = title_norm.split()[:3]
        key_parts = words

    return "-".join(key_parts)


# -----------------------------
# AGGREGATE PRODUCTS
# -----------------------------
def aggregate_products(products):

    grouped = defaultdict(list)

    # group by strict key
    for product in products:
        key = generate_group_key(product["title"])
        grouped[key].append(product)

    results = []

    for key, items in grouped.items():

        # pick best price
        valid_prices = [p for p in items if p["price_value"] > 0]

        if valid_prices:
            best_product = min(valid_prices, key=lambda x: x["price_value"])
        else:
            best_product = items[0]

        # choose best representative title (longest)
        representative_title = max(
            items,
            key=lambda x: len(x["title"])
        )["title"]

        results.append({
            "title": representative_title,
            "best_price": best_product["price_display"],
            "best_platform": best_product["platform"],
            "best_url": best_product["url"],
            "offers": items
        })

    return results