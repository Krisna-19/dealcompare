import re
from difflib import SequenceMatcher

STOP_WORDS = {
    "for", "with", "and", "the", "in", "of", "to",
    "best", "new", "latest", "original",
    "buy", "sale", "offer"
}


def clean_title(title: str):
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", " ", title)
    words = [w for w in title.split() if w not in STOP_WORDS and len(w) > 2]
    return words


def token_similarity(a, b):
    set_a = set(clean_title(a))
    set_b = set(clean_title(b))

    if not set_a or not set_b:
        return 0

    overlap = len(set_a & set_b)
    total = len(set_a | set_b)

    return overlap / total


def string_similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def hybrid_similarity(a, b):
    token_score = token_similarity(a, b)
    string_score = string_similarity(a, b)

    # Weighted combination
    return (token_score * 0.6) + (string_score * 0.4)


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

            similarity = hybrid_similarity(
                product["title"],
                other["title"]
            )

            if similarity > 0.55:  # tuned threshold
                group.append(other)
                used.add(j)

        grouped.append(group)

    final_results = []

    for group in grouped:
        best = min(
            group,
            key=lambda x: x["price_value"]
            if x["price_value"] > 0 else 999999
        )

        final_results.append({
            "title": best["title"],
            "best_price": best["price_display"],
            "best_platform": best["platform"],
            "best_url": best["url"],
            "offers": group
        })

    return final_results
