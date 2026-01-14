import re
import os
import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

app = FastAPI(title="DealCompare API")

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        "product_url": "https://myntra.com/levis-tshirt"
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
        "product_url": "https://ajio.com/levis-tshirt"
    }
]

# ---------- HELPERS ----------
def normalize(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", text.lower())

def price_value(p):
    return int(p["price"].replace("₹", "").replace(",", ""))

# ---------- ROUTES ----------
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

    q = normalize(query)

    filtered = [
        p for p in PRODUCTS
        if q in normalize(p["name"])
        or q in normalize(p["brand"])
        or q in normalize(p["category"])
    ]

    if not filtered:
        return {"message": "Found 0 best deals", "results": []}

    min_price = min(price_value(p) for p in filtered)

    # ✅ CALCULATE SCORE
    for p in filtered:
        rating_score = (p["rating"] / 5) * 0.6
        price_score = (min_price / price_value(p)) * 0.4
        p["score"] = round(rating_score + price_score, 3)

    # ✅ BEST DEAL = highest score
    best = max(filtered, key=lambda x: x["score"])
    others = [p for p in filtered if p != best]

    return {
        "message": f"Found 1 best deals",
        "results": [{
            "product_name": best["name"],
            "brand": best["brand"],
            "best_deal": best,
            "other_offers": others
        }]
    }

@app.get("/suggest")
def suggest(query: str):
    q = normalize(query)
    suggestions = []

    for p in PRODUCTS:
        if q in normalize(p["name"]):
            suggestions.append(p["name"])

    return list(dict.fromkeys(suggestions))[:5]

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
