from services.ranking_service import calculate_match_score


MATCH_THRESHOLD = 75  # strict grouping threshold


def aggregate_products(products):
    """
    Groups similar products across platforms,
    selects best price, and returns structured comparison result.
    """

    grouped = []
    used_indexes = set()

    for i, product in enumerate(products):

        if i in used_indexes:
            continue

        current_group = [product]
        used_indexes.add(i)

        for j, other in enumerate(products):

            if j in used_indexes:
                continue

            score = calculate_match_score(
                product["title"],
                other["title"]
            )

            if score >= MATCH_THRESHOLD:
                current_group.append(other)
                used_indexes.add(j)

        grouped.append(current_group)

    final_results = []

    for group in grouped:

        # Filter products with valid price
        valid_prices = [
            p for p in group if p.get("price_value", 0) > 0
        ]

        if valid_prices:
            best = min(valid_prices, key=lambda x: x["price_value"])
        else:
            # fallback if all price_value are 0
            best = group[0]

        final_results.append({
            "title": best["title"],
            "best_price": best["price_display"],
            "best_platform": best["platform"],
            "best_url": best["url"],
            "offers": group
        })

    return final_results