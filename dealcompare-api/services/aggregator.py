import re
from collections import defaultdict

STOP_WORDS = {
    "best", "top", "new", "latest", "offer", "sale",
    "for", "with", "and", "the", "in", "on"
}


def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    words = text.split()
    words = [w for w in words if w not in STOP_WORDS]
    return set(words)


def similarity_score(title1, title2):
    words1 = normalize(title1)
    words2 = normalize(title2)

    if not words1 or not words2:
        return 0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union)


def aggregate_products(products):

    groups = []
    used = set()

    for i, product in enumerate(products):
        if i in used:
            continue

        group = [product]
        used.add(i)

        for j, other in enumerate(products):
            if j in used:
                continue

            score = similarity_score(product["title"], other["title"])

            if score > 0.6:   # tuned threshold
                group.append(other)
                used.add(j)

        groups.append(group)

    final_results = []

    for group in groups:
        valid_prices = [p for p in group if p["price_value"] > 0]

        if valid_prices:
            best = min(valid_prices, key=lambda x: x["price_value"])
        else:
            best = group[0]

        final_results.append({
            "title": best["title"],
            "best_price": best["price_display"],
            "best_platform": best["platform"],
            "best_url": best["url"],
            "offers": group
        })

    return final_results
