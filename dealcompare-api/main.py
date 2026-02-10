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

def is_valid_product(p: dict) -> bool:
    return bool(
        p.get("product_name")
        and p.get("product_url")
        and p.get("platform")
    )

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
    products = [p for p in products if is_valid_product(p)]

    if not products:
        return {"message": "No products found", "results": []}

    # Score safely
    for p in products:
        p["score"] = score_product(p)

    # Sort by score (best first)
    products.sort(key=lambda x: x["score"], reverse=True)

    # Limit to TOP 3
    products = products[:3]

    return {
        "message": "Top matching products found",
        "results": products,
    }
