import re


def normalize_text(text: str) -> str:
    """
    Clean product title for comparison
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_model_number(text: str):
    """
    Extract model numbers like:
    iPhone 15
    Samsung S23
    """
    match = re.search(r"\b\d{1,3}\b", text)
    return match.group() if match else None


def extract_storage(text: str):
    """
    Extract storage values like:
    128GB
    256GB
    1TB
    """
    match = re.search(r"(\d+)\s?(gb|tb)", text.lower())

    if match:
        return match.group(1) + match.group(2)

    return None


def extract_product_info(text):

    text = text.lower()

    brand = None
    model = None
    storage = None

    if "iphone" in text:
        brand = "apple"

    model_match = re.search(r'iphone\s*(\d+)', text)
    if model_match:
        model = model_match.group(1)

    storage_match = re.search(r'(\d+)\s?gb', text)
    if storage_match:
        storage = storage_match.group(1) + "gb"

    return brand, model, storage

def generate_product_key(title):

    brand, model, storage = extract_product_info(title)

    if not brand or not model:
        return None

    key = f"{brand}-iphone-{model}"

    if storage:
        key += f"-{storage}"

    return key