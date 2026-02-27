import re


def normalize_text(text: str) -> str:
    """
    Clean and normalize text for comparison
    """
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_model_number(text: str):
    """
    Extract model numbers like:
    iPhone 15, iPhone 14, etc.
    """
    match = re.search(r"\b\d{1,2}\b", text)
    return match.group() if match else None


def extract_storage(text: str):
    """
    Extract storage values like:
    128GB, 256GB, 512GB
    """
    match = re.search(r"(\d+)\s?(gb|tb)", text.lower())

    if match:
        return match.group(1) + match.group(2)

    return None