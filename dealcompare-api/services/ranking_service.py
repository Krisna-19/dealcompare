import re
from rapidfuzz import fuzz


# Extract model numbers like 15, 14 Pro, S23, etc.
def extract_model_numbers(text: str):
    return re.findall(r'\b\d+\b', text)


# Extract storage values like 128GB, 256 GB
def extract_storage(text: str):
    return re.findall(r'\b\d+\s?GB\b', text, re.IGNORECASE)


# Extract brand (basic for now)
def extract_brand(text: str):
    brands = ["apple", "samsung", "oneplus", "iqoo", "realme", "xiaomi"]
    text_lower = text.lower()
    for brand in brands:
        if brand in text_lower:
            return brand
    return None


def calculate_match_score(query: str, title: str):

    query_lower = query.lower()
    title_lower = title.lower()

    total_score = 0

    # -------------------------
    # 1️⃣ Brand Matching (40%)
    # -------------------------
    query_brand = extract_brand(query)
    title_brand = extract_brand(title)

    if query_brand and title_brand:
        if query_brand == title_brand:
            total_score += 40
        else:
            return 0  # completely different brand → reject

    # -------------------------
    # 2️⃣ Model Number Matching (30%)
    # -------------------------
    query_models = extract_model_numbers(query)
    title_models = extract_model_numbers(title)

    if query_models:
        if any(model in title_models for model in query_models):
            total_score += 30
        else:
            total_score -= 20

    # -------------------------
    # 3️⃣ Storage Matching (20%)
    # -------------------------
    query_storage = extract_storage(query)
    title_storage = extract_storage(title)

    if query_storage:
        if any(storage.lower() in [s.lower() for s in title_storage] for storage in query_storage):
            total_score += 20
        else:
            total_score -= 10

    # -------------------------
    # 4️⃣ Text Similarity (10%)
    # -------------------------
    similarity = fuzz.partial_ratio(query_lower, title_lower)
    total_score += similarity * 0.1  # max 10 points

    return total_score