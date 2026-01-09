from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Query
from typing import Optional

app = FastAPI(title="DealCompare API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",

        # Future production domains (add later)
        # "https://bestdeals.in",
        # "https://www.bestdeals.in",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
PRODUCTS = [
    {
        "id": 1,
        "name": "Apple iPhone 15 (128GB, Blue)",
        "brand": "Apple",
        "category": "Electronics",
        "price": "₹65,999",
        "platform": "Amazon",
        "rating": 4.8,
        "delivery_days": 1,
        "product_url": "https://amazon.in/iphone15"
    },
    {
        "id": 2,
        "name": "Apple iPhone 15 (128GB, Blue)",
        "brand": "Apple",
        "category": "Electronics",
        "price": "₹64,900",
        "platform": "Flipkart",
        "rating": 4.7,
        "delivery_days": 4,
        "product_url": "https://flipkart.com/iphone15"
    }
]

@app.get("/")
def root():
    return {"status": "DealCompare API running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/search")
def search(query: Optional[str] = Query(None)):
    filtered = PRODUCTS
    if query:
        q = query.lower()
        filtered = [
            p for p in PRODUCTS
            if q in p["name"].lower()
            or q in p["brand"].lower()
            or q in p["category"].lower()
        ]

    groups = {}
    for p in filtered:
        key = (p["name"], p["brand"])
        groups.setdefault(key, []).append(p)

    results = []
    for (name, brand), offers in groups.items():
        def price(p): return int(p["price"].replace("₹", "").replace(",", ""))
        best = min(offers, key=price)
        others = [o for o in offers if o != best]

        results.append({
            "product_name": name,
            "brand": brand,
            "best_deal": best,
            "other_offers": others
        })

    return {
        "message": f"Found {len(results)} best deals",
        "results": results
    }

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
