from collections import defaultdict
from difflib import SequenceMatcher

def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

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

            if similarity(product["title"], other["title"]) > 0.75:
                group.append(other)
                used.add(j)

        grouped.append(group)

    final_results = []

    for group in grouped:
        best = min(group, key=lambda x: x["price_value"] if x["price_value"] > 0 else 999999)

        final_results.append({
            "title": best["title"],
            "best_price": best["price_display"],
            "best_platform": best["platform"],
            "best_url": best["url"],
            "offers": group
        })

    return final_results
