from collections import defaultdict
from difflib import SequenceMatcher


def similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def aggregate_products(products):
    grouped = []
    used = set()

    # ---- GROUP SIMILAR PRODUCTS ----
    for i, product in enumerate(products):
        if i in used:
            continue

        group = [product]
        used.add(i)

        for j, other in enumerate(products):
            if j in used:
                continue

            score = similarity(product.get("title", ""), other.get("title", ""))

            if score > 0.75:
                group.append(other)
                used.add(j)

        grouped.append(group)

    # ---- PICK BEST OFFER FROM EACH GROUP ----
    final_results = []

    for group in grouped:

        valid_prices = [
            p for p in group
            if p.get("price_value") and p["price_value"] > 0
        ]

        if valid_prices:
            best = min(valid_prices, key=lambda x: x["price_value"])
        else:
            best = group[0]

        final_results.append({
            "title": best.get("title"),
            "best_price": best.get("price_display"),
            "best_platform": best.get("platform"),
            "best_url": best.get("url"),
            "offers": [
                {
                    "platform": p.get("platform"),
                    "price": p.get("price_display"),
                    "url": p.get("url")
                }
                for p in group
            ]
        })

    return final_results
