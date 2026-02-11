from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import re

app = FastAPI(title="DealCompare API")

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CONFIG
# =========================
AMAZON_TAG = "dealcompare19-21"


# =========================
# UTILS
# =========================
def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_amazon_search_url(query: str) -> str:
    q = query.replace(" ", "+")
    return f"https://www.amazon.in/s?k={q}&tag={AMAZON_TAG}"


def score_product(index: int) -> float:
    """
    For now:
    Amazon search order = ranking signal
    Earlier result = better score
    """
    return round(1 / (index + 1), 3)


# =========================
# MOCK AMAZON FETCH (Stage 1)
# =========================
def fetch_amazon_products(query: str) -> List[dict]:
    """
    Stage 1:
    We simulate structured products based on search query.
    Later this will be replaced with real PA-API.
    """

    base_url = build_amazon_search_url(query)

    products = []

    for i in range(5):
        products.append({
            "title": f"{query.title()} - Option {i+1}",
            "platform": "Amazon",
            "price_display": "Check price",
            "price_value": 0,
            "rating": None,
            "image": "",
            "url": base_url,
            "category": "General",
            "score": score_product(i)
        })

    return products


# =========================
# SEARCH ENDPOINT
# =========================
@app.get("/search")
def search(query: str = Query(...)):
    query = normalize(query)

    if not query:
        return {"message": "Invalid query", "results": []}

    products = fetch_amazon_products(query)

    if not products:
        return {"message": "No products found", "results": []}

    return {
        "message": "Top matching products found",
        "results": products
    }
