import os
import re
from typing import Optional, List

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from affiliates.amazon_links import build_amazon_search_link

# --------------------------------------------------
# APP SETUP
# --------------------------------------------------
app = FastAPI(title="DealCompare API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://dealcompare.in",
        "https://www.dealcompare.in",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_category(query: str) -> str:
    q = normalize(query)

    if any(x in q for x in ["shirt", "tshirt", "jeans", "sweatshirt", "jacket", "dress"]):
        return "Fashion"
    if any(x in q for x in ["bag", "backpack", "laptop", "messenger", "case"]):
        return "Electronics"
    if any(x in q for x in ["serum", "cream", "skincare", "facewash", "lotion"]):
        return "Beauty"
    if any(x in q for x in ["phone", "mobile", "charger", "earbuds", "headphones"]):
        return "Electronics"

    return "General"


def generate_top_products(query: str) -> List[str]:
    """
    Generic intent expansion – works for ALL products.
    """
    base = normalize(query)

    return [
        base,
        f"best {base}",
        f"top rated {base}",
    ]


# --------------------------------------------------
# PLATFORM BUILDERS (SAFE – NO SCRAPING)
# --------------------------------------------------
def build_myntra_offer(query: str) -> dict:
    return {
        "platform": "Myntra",
        "price": "Check price",
        "rating": None,
        "product_url": f"https://www.myntra.com/{query.replace(' ', '-')}",
    }


def build_ajio_offer(query: str) -> dict:
    return {
        "platform": "Ajio",
        "price": "Check price",
        "rating": None,
        "product_url": f"https://www.ajio.com/search/?text={query}",
    }


def build_amazon_offer(query: str) -> dict:
    return {
        "platform": "Amazon",
        "price": "Check price",
        "rating": None,
        "product_url": build_amazon_search_link(query),
    }


# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@app.get("/")
def root():
    return {"status": "DealCompare API running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/search")
def search(query: Optional[str] = Query(None)):
    if not query:
        return {"message": "No query provided", "results": []}

    clean_query = normalize(query)
    category = detect_category(clean_query)

    top_products = generate_top_products(clean_query)
    results = []

    for product_name in top_products:
        offers = [
            build_myntra_offer(product_name),
            build_ajio_offer(product_name),
            build_amazon_offer(product_name),
        ]

        results.append({
            "product_name": product_name,
            "offers": offers,
        })

    return {
        "message": "Top 3 matching products found",
        "category": category,
        "query": query,
        "results": results,
    }


# --------------------------------------------------
# RUN
# --------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
