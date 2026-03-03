def detect_category(query: str) -> str:
    q = query.lower()

    if any(word in q for word in ["shoe", "shirt", "jeans", "bag", "fashion"]):
        return "Fashion"

    if any(word in q for word in ["laptop", "phone", "tv", "electronics"]):
        return "Electronics"

    if any(word in q for word in ["serum", "cream", "skincare", "beauty"]):
        return "Beauty"

    return "General"
