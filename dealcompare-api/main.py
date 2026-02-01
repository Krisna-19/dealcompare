import os
import time
import re
import sys
from difflib import SequenceMatcher
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from scrapers.flipkart import scrape_flipkart
from scrapers.myntra import scrape_myntra
from affiliates.amazon_links import build_amazon_search_link
from seed_data import SEED_PRODUCTS


# --------------------------------------------------
# App setup
# --------------------------------------------------

app = FastAPI(title="DealCompare API")

CACHE = {}
CACHE_TTL = 300  # 5 minutes

# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --------------------------------------------------
# Helpers
# --------------------------------------------------

def normalize(text: str) -> str:
    """
    Normalize text for better matching:
    - lowercase
    - remove special characters
    """
    return re.sub(r"[^a-z0-9 ]", "", text.lower())

def similarity(a: str, b: str) -> float:
    """
    Compute similarity score between two product names
    """
    a = normalize(a)
    b = normalize(b)
    return SequenceMatcher(None, a, b).ratio()

def pick_best_product(products: list, query: str, min_score: float = 0.4):
    """
    Pick ONE best matching product from a website
    """
    if not products:
        return None

    scored = []
    for p in products:
        name = p.get("name", "")
        score = similarity(name, query)
        scored.append((score, p))

    scored.sort(reverse=True, key=lambda x: x[0])
    best_score, best_product = scored[0]

    if best_score < min_score:
        return None

    return best_product

def parse_price(price: str) -> int:
    try:
        return int(price.replace("₹", "").replace(",", ""))
    except:
        return 0

# --------------------------------------------------
# Routes
# --------------------------------------------------
def simplify_query(query: str) -> str:
    words = normalize(query).split()
    return " ".join(words[:3])  # take first 2–3 keywords

@app.get("/")
def root():
    return {"status": "DealCompare API running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/search")
def search(query: Optional[str] = Query(None)):
    if not query:
        return {"message": "No query", "results": []}

    q = query.strip()
    scrape_q = simplify_query(q)
    offers = []

    # ---- SCRAPING ----
    try:
        myntra_products = scrape_myntra(scrape_q)
        best_myntra = pick_best_product(myntra_products, q)
        if best_myntra:
            best_myntra["platform"] = "Myntra"
            best_myntra["price_value"] = parse_price(best_myntra["price"])
            offers.append(best_myntra)
    except:
        pass

    try:
        flipkart_products = scrape_flipkart(scrape_q)
        best_flipkart = pick_best_product(flipkart_products, q)
        if best_flipkart:
            best_flipkart["platform"] = "Flipkart"
            best_flipkart["price_value"] = parse_price(best_flipkart["price"])
            offers.append(best_flipkart)
    except:
        pass

    # ✅ ADD FALLBACK HERE
    if not offers:
        key = normalize(q).replace(" ", "")
        if key in SEED_PRODUCTS:
            offers = SEED_PRODUCTS[key]

    # ❌ ONLY NOW decide "No deals found"
    if not offers:
        return {"message": "No deals found", "results": []}

    # ---- BUILD RESPONSE ----
    best = min(offers, key=lambda x: x["price_value"])
    others = [p for p in offers if p is not best]

    return {
        "message": "Found best deal",
        "results": [{
            "product_name": best["name"],
            "brand": "N/A",
            "best_deal": best,
            "other_offers": others,
            "amazon_affiliate_url": build_amazon_search_link(q)
        }]
    }


    CACHE[q] = {
        "time": now,
        "data": response
    }

    return response


# --------------------------------------------------
# Run
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
