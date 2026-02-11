def score_product(index: int) -> float:
    """
    Earlier search result = higher score.
    """
    return round(1 / (index + 1), 3)
