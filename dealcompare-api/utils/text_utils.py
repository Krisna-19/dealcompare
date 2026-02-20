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




BRANDS = [
    "apple", "samsung", "oneplus", "xiaomi",
    "realme", "sony", "dell", "hp", "lenovo"
]

def extract_brand(title: str):
    title_lower = title.lower()
    for brand in BRANDS:
        if brand in title_lower:
            return brand
    return None


def extract_storage(title: str):
    match = re.search(r'(\d+)\s?(gb|tb)', title.lower())
    if match:
        return match.group(1) + match.group(2)
    return None

def extract_model_number(title: str):
    # Detect things like S24, 15 Pro, 14 Plus
    match = re.search(r'\b([a-zA-Z]*\d+[a-zA-Z]*)\b', title)
    if match:
        return match.group(1)
    return None        