import os
import re
import time
from typing import Optional, List

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

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


def extract_keywords(query: str) -> List[str]:
    STOP_WORDS = {
        "for", "with", "and", "or", "the", "men", "women",
        "professional", "original", "new"
    }
    words = normalize(query).split()
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def detect_category(query: str) -> str:
    q = normalize(query)

    if any(x in q for x in ["tshirt", "shirt", "jeans", "sweatshirt", "jacket"]):
        return "Fashion"
    if any(x in q for x in ["laptop", "bag", "backpack", "messenger"]):
        return "Electronics"
    if any(x in q for x in ["serum", "cream", "skincare", "facewash"]):
        return "Beauty"
    if any(x in q for x in ["phone", "mobile", "charger", "earbuds"]):
        return "Electronics"

    return "General"


# --------------------------------------------------
# CORE SEARCH LOGIC
# --------------------------------------------------
def build_myntra_search(query: str) -> dict:
    return {
        "platform": "Myntra",
        "price": "Check price",
        "rating": None,
        "product_url": f"https://www.myntra.com/{query.replace(' ', '-')}",
    }


def build_ajio_search(query: str) -> dict:
    return {
        "platform": "Ajio",
        "price": "Check price",
        "rating": None,
        "product_url": f"https://www.ajio.com/search/?text={query}",
    }


def build_amazon_products(query: str) -> List[dict]:
    base_url = build_amazon_search_link(query)

    # Top 3 Amazon placeholders (safe & compliant)
    return [
        {
            "platform": "Amazon",
            "price": "Check price",
            "rating": None,
            "product_url": base_url,
        },
        {
            "platform": "Amazon",
            "price": "Check price",
            "rating": None,
            "product_url": base_url,
        },
        {
            "platform": "Amazon",
            "price": "Check price",
            "rating": None,
            "product_url": base_url,
        },
    ]


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

    query_clean = normalize(query)
    keywords = extract_keywords(query)
    category = detect_category(query)

    results = []

    # 1️⃣ Myntra
    results.append(build_myntra_search(query_clean))

    # 2️⃣ Ajio
    results.append(build_ajio_search(query_clean))

    # 3️⃣ Amazon (Top 3)
    amazon_products = build_amazon_products(query_clean)
    results.extend(amazon_products)

    response = {
        "message": "Top matching products found",
        "category": category,
        "query": query,
        "results": [
            {
                "product_name": query,
                "offers": results,
            }
        ],
    }

    return response


# --------------------------------------------------
# RUN
# --------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
