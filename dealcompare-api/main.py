import re
import os
import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

app = FastAPI(title="DealCompare API")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- DATA ----------------
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

# ---------------- HELPERS ----------------
def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    return re.sub(r"[^a-z0-9]", "", text)

def price_to_int(price: str) -> int:
    return int(price.replace("₹", "").replace(",", ""))

# ---------------- SEARCH ----------------
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

    # Group by product
    groups = {}
    for p in filtered:
        key = (p["name"], p["brand"])
        groups.setdefault(key, []).append(p)

    results = []

    for (name, brand), offers in groups.items():
        prices = [price_to_int(o["price"]) for o in offers]
        ratings = [o["rating"] for o in offers]

        min_price = min(prices)
        max_price = max(prices)
        min_rating = min(ratings)
        max_rating = max(ratings)

        # Score calculation
        for o in offers:
            price = price_to_int(o["price"])
            rating = o["rating"]

            price_score = (
                1 if max_price == min_price
                else (max_price - price) / (max_price - min_price)
            )

            rating_score = (
                1 if max_rating == min_rating
                else (rating - min_rating) / (max_rating - min_rating)
            )

            o["score"] = round((price_score * 0.7) + (rating_score * 0.3), 3)

        # Best deal = highest score
        offers_sorted = sorted(offers, key=lambda x: x["score"], reverse=True)
        best = offers_sorted[0]
        others = offers_sorted[1:]

        results.append({
            "product_name": name,
            "brand": brand,
            "best_deal": {
                **best,
                "score": best["score"]
            },
            "other_offers": [
                {**o, "score": o["score"]} for o in others
            ]
        })

    return {
        "message": f"Found {len(results)} best deals",
        "results": results
    }

# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status": "DealCompare API running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
