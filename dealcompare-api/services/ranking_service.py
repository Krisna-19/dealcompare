def score_product(index: int) -> float:
    """
    Earlier search result = higher score.
    """
    return round(1 / (index + 1), 3)

from rapidfuzz import fuzz
from utils.text_utils import (
    extract_brand,
    extract_storage,
    extract_model_number
)

def calculate_match_score(title1, title2):

    brand1 = extract_brand(title1)
    brand2 = extract_brand(title2)

    # Brand must match
    if brand1 and brand2 and brand1 != brand2:
        return 0

    storage1 = extract_storage(title1)
    storage2 = extract_storage(title2)

    # If both have storage and not equal → reject
    if storage1 and storage2 and storage1 != storage2:
        return 0

    model1 = extract_model_number(title1)
    model2 = extract_model_number(title2)

    model_score = 100 if model1 and model2 and model1 == model2 else 0

    title_score = fuzz.token_sort_ratio(title1, title2)

    final_score = (
        0.5 * title_score +
        0.3 * model_score +
        0.2 * (100 if brand1 == brand2 else 0)
    )

    return final_score