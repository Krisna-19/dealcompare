import re
from difflib import SequenceMatcher
from collections import defaultdict


# -----------------------------
# TEXT NORMALIZATION
# -----------------------------
def normalize(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return text.strip()


# -----------------------------
# EXTRACT IMPORTANT TOKENS
# (model numbers, ml, gb, inch etc.)
# -----------------------------
def extract_model_tokens(text):
    text = text.lower()

    # capture:
    # 350ml, 14l, 128gb, 6gb, sc04, m2, 15.6inch etc.
    tokens = re.findall(r'\b[a-z]*\d+[a-z]*\b', text)

    return set(tokens)


# -----------------------------
# HYBRID SIMILARITY
# -----------------------------
def hybrid_similarity(title1, title2):
    t1 = normalize(title1)
    t2 = normalize(title2)

    # Base similarity
    base_score = SequenceMatcher(None, t1, t2).ratio()

    # Model token similarity
    tokens1 = extract_model_tokens(t1)
    tokens2 = extract_model_tokens(t2)

    if tokens1 and tokens2:
        common = tokens1.intersection(tokens2)
        model_score = len(common) / max(len(tokens1), len(tokens2))
    else:
        model_score = 0

    # Weighted score
    final_score = (0.7 * base_score) + (0.3 * model_score)

    return final_score


# -----------------------------
# AGGREGATION
# -----------------------------
def aggregate_products(products):

    grouped = []
    used = set()

    for i, product in enumerate(products):

        if i in used:
            continue

        group = [product]
        used.add(i)

        for j, other in enumerate(products):

            if j in used:
                continue

            score = hybrid_similarity(product["title"], other["title"])

            if score > 0.65:  # slightly stronger threshold
                group.append(other)
                used.add(j)

        grouped.append(group)

    final_results = []

    for group in grouped:

        best = min(
            group,
            key=lambda x: x["price_value"] if x["price_value"] > 0 else 999999
        )

        final_results.append({
            "title": best["title"],
            "best_price": best["price_display"],
            "best_platform": best["platform"],
            "best_url": best["url"],
            "offers": group
        })

    return final_results
