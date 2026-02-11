from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import re

# ======================
# APP SETUP
# ======================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# HELPERS
# ======================
STOP_WORDS = {
    "for", "with", "and", "or", "the", "in", "on", "of",
    "by", "to", "from", "men", "women", "kids"
}

def extract_keywords(text: str) -> set:
    words = normalize(text).split()
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}

def match_confidence(query: str, product_name: str) -> float:
    q_words = extract_keywords(query)
    p_words = extract_keywords(product_name)

    if not q_words or not p_words:
        return 0.0

    common = q_words.intersection(p_words)
    return round(len(common) / len(q_words), 3)

def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def safe_float(val, default=0.0):
    try:
        return float(val)
    except:
        return default

def score_product(p: dict) -> float:
    """
    Safe scoring:
    - Rating helps
    - Lower price helps
    """
    rating = safe_float(p.get("rating"), 0)
    price = safe_float(p.get("price_value"), 999999)

    return round((rating * 2) - (price / 1000), 3)

def is_valid_product(p: dict, query: str) -> bool:
    if not p.get("product_name") or not p.get("product_url"):
        return False

    confidence = match_confidence(query, p["product_name"])
    p["match_confidence"] = confidence

    # Reject weak matches
    return confidence >= 0.3


# ======================
# SCRAPERS (SAFE FALLBACK VERSION)
# ======================

def amazon_products(query: str) -> List[dict]:
    q = query.replace(" ", "+")
    return [
        {
            "product_name": query,
            "price": "Check price",
            "price_value": 0,
            "rating": None,
            "platform": "Amazon",
            "product_url": f"https://www.amazon.in/s?k={q}&tag=dealcompare19-21",
        }
    ]

def myntra_products(query: str) -> List[dict]:
    q = query.replace(" ", "%20")
    return [
        {
            "product_name": query,
            "price": "Check price",
            "price_value": 0,
            "rating": None,
            "platform": "Myntra",
            "product_url": f"https://www.myntra.com/{q}",
        }
    ]

def ajio_products(query: str) -> List[dict]:
    q = query.replace(" ", "%20")
    return [
        {
            "product_name": query,
            "price": "Check price",
            "price_value": 0,
            "rating": None,
            "platform": "Ajio",
            "product_url": f"https://www.ajio.com/search/?text={q}",
        }
    ]

# ======================
# SEARCH API
# ======================

@app.get("/search")
def search(query: str):
    query = normalize(query)

    if not query:
        return {"message": "Invalid query", "results": []}

    products = []

    # Collect equally from all platforms
    products += amazon_products(query)
    products += myntra_products(query)
    products += ajio_products(query)

    # Filter invalid junk
    valid_products = []

    for p in products:
        if is_valid_product(p, query):
            p["score"] = score_product(p)
            valid_products.append(p)

    if not valid_products:
        return {"message": "No products found", "results": []}

    # Score safely
    for p in products:
        p["score"] = score_product(p)

    # Sort by score (best first)
    valid_products.sort(
    key=lambda x: (x["match_confidence"], x["score"]),
    reverse=True
    )

    results = valid_products[:3]

    return {
        "message": "Top matching products found",
        "results": products,
    }
