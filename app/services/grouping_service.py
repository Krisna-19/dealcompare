from difflib import SequenceMatcher

from app.core.config import get_settings
from app.utils.text_utils import normalize_text


def similarity_score(title_a, title_b):
    """
    Similarity between two product titles as a float in [0.0, 1.0].
    """
    return SequenceMatcher(
        None, normalize_text(title_a), normalize_text(title_b)
    ).ratio()


def group_products(products):
    grouped = []
    used = set()

    for i, p1 in enumerate(products):
        if i in used:
            continue

        group = [p1]
        used.add(i)

        for j, p2 in enumerate(products):
            if j in used:
                continue

            score = similarity_score(p1.title, p2.title)

            if score > get_settings().group_similarity_threshold:
                group.append(p2)
                used.add(j)

        grouped.append(group)

    return grouped
