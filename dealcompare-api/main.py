import re
import os
import uvicorn
from seed_data import SEED_PRODUCTS
import time
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from scrapers.flipkart import scrape_flipkart
from scrapers.myntra import scrape_myntra
from scoring import calculate_score
from affiliates.amazon_links import build_amazon_search_link



app = FastAPI(title="DealCompare API")
CACHE = {}
CACHE_TTL = 300  # seconds (5 minutes)

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://dealcompare.pages.dev",
        "https://dealcompare.in",
        "https://www.dealcompare.in",
    ],
    allow_origin_regex=r"https://.*\.pages\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DATA ----------
PRODUCTS = [
    {
        "id": 5,
        "name": "Levi's Men's Printed T-Shirt",
        "brand": "Levi's",
        "category": "Fashion",
        "price": "₹899",
        "platform": "Myntra",
        "rating": 4.3,
        "delivery_days": 3,
        "product_url": "https://myntra.com/levis-tshirt",
    },
    {
        "id": 6,
        "name": "Levi's Men's Printed T-Shirt",
        "brand": "Levi's",
        "category": "Fashion",
        "price": "₹949",
        "platform": "Ajio",
        "rating": 4.2,
        "delivery_days": 4,
        "product_url": "https://ajio.com/levis-tshirt",
    },
]

# ---------- HELPERS ----------
def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower()) if text else ""

def price_value(product: dict) -> int:
    try:
        return int(product["price"].replace("₹", "").replace(",", ""))
    except Exception:
        return 0

# ---------- ROUTES ----------
@app.get("/")
def root():
    return {"status": "DealCompare API running"}

@app.get("/health")
def health():
    return {"status": "healthy"}
amazon_url = build_amazon_search_link(query)


@app.get("/search")
def search(query: Optional[str] = Query(None)):
    if not query:
        return {"message": "No query", "results": []}

    q = query.lower().strip()
    now = time.time()

    # 1️⃣ Return cached result if exists
    if q in CACHE and now - CACHE[q]["time"] < CACHE_TTL:
        return CACHE[q]["data"]

    # 2️⃣ Try real scraping
    flipkart = []
    myntra = []

    try:
        flipkart = scrape_flipkart(q)
    except:
        pass

    try:
        myntra = scrape_myntra(q)
    except:
        pass

    products = flipkart + myntra

    # 3️⃣ If scraping FAILED → use seed data
    if not products:
        seed_key = q.replace(" ", "")
        if seed_key in SEED_PRODUCTS:
            products = SEED_PRODUCTS[seed_key]
        else:
            return {"message": "No deals found", "results": []}

    # 4️⃣ Price parsing + scoring
    valid = []
    for p in products:
        try:
            p["price_value"] = int(p["price"].replace("₹", "").replace(",", ""))
            valid.append(p)
        except:
            continue

    min_price = min(p["price_value"] for p in valid)
    min_delivery = min(p.get("delivery_days", 4) for p in valid)

    for p in valid:
        p["score"] = round(
            (p.get("rating", 3.5) / 5) * 0.4 +
            (min_price / p["price_value"]) * 0.4 +
            (min_delivery / p.get("delivery_days", 4)) * 0.2,
            3
        )

    best = max(valid, key=lambda x: x["score"])
    others = [p for p in valid if p is not best]

    response = {
        "message": "Found best deal",
        "results": [{
            "product_name": best["name"],
            "brand": "N/A",
            "best_deal": best,
            "other_offers": others
        }]
    }

    # 5️⃣ Cache response
    CACHE[q] = {
        "time": now,
        "data": response
    }

    return response



@app.get("/suggest")
def suggest(query: str):
    q = normalize(query)
    suggestions = []

    for p in PRODUCTS:
        if q in normalize(p["name"]):
            suggestions.append(p["name"])

    # remove duplicates, keep order
    return list(dict.fromkeys(suggestions))[:5]

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
