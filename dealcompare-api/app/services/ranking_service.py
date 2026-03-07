import re
from rapidfuzz import fuzz
from app.utils.text_utils import normalize_text, extract_model_number, extract_storage


# -----------------------------
# TEXT NORMALIZATION
# -----------------------------
def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# -----------------------------
# EXTRACT MODEL NUMBER
# -----------------------------
def extract_model_number(text: str):
    """
    Extracts numbers like:
    15, 14, 13, 17 etc from 'iPhone 15'
    """
    match = re.search(r"\b\d{1,2}\b", text)
    return match.group() if match else None


# -----------------------------
# EXTRACT STORAGE (128GB etc)
# -----------------------------
def extract_storage(text: str):
    match = re.search(r"(\d{2,4})\s?gb", text.lower())
    return match.group(1) if match else None


# -----------------------------
# STRICT MODEL MATCH CHECK
# -----------------------------
def strict_model_match(query: str, title: str):

    query = normalize(query)
    title = normalize(title)

    query_model = extract_model_number(query)
    title_model = extract_model_number(title)

    query_storage = extract_storage(query)
    title_storage = extract_storage(title)

    # MODEL must match if exists
    if query_model and title_model:
        if query_model != title_model:
            return False

    # STORAGE must match if exists
    if query_storage and title_storage:
        if query_storage != title_storage:
            return False

    return True


# -----------------------------
# MATCH SCORE
# -----------------------------
def calculate_match_score(query: str, title: str):

    query_norm = normalize_text(query)
    title_norm = normalize_text(title)

    # Base similarity
    score = fuzz.token_set_ratio(query_norm, title_norm)

    # Extract important tokens
    query_model = extract_model_number(query_norm)
    title_model = extract_model_number(title_norm)

    query_storage = extract_storage(query_norm)
    title_storage = extract_storage(title_norm)

    # Model match bonus
    if query_model and title_model and query_model == title_model:
        score += 20

    # Storage match bonus
    if query_storage and title_storage and query_storage == title_storage:
        score += 20

    return score