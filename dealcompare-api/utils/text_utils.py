import re

def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def similarity_score(a: str, b: str) -> float:
    a = normalize_text(a)
    b = normalize_text(b)

    set_a = set(a.split())
    set_b = set(b.split())

    if not set_a or not set_b:
        return 0.0

    intersection = set_a.intersection(set_b)
    union = set_a.union(set_b)

    return len(intersection) / len(union)
