import re
import os
import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from scrapers.flipkart import scrape_flipkart
from scrapers.myntra import scrape_myntra
from scoring import calculate_score


app = FastAPI(title="DealCompare API")

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
@app.get("/search")
def search(query: Optional[str] = Query(None)):
    try:
        if not query:
            return {"message": "No query", "results": []}

        flipkart = []
        myntra = []

        try:
            flipkart = scrape_flipkart(query)
        except:
            pass

        try:
            myntra = scrape_myntra(query)
        except:
            pass


        all_products = flipkart + myntra

        if not all_products:
            return {"message": "No deals found", "results": []}

        valid_products = []

        for p in all_products:
            try:
                p["price_value"] = int(
                    p["price"].replace("₹", "").replace(",", "").strip()
                )
                if p["price_value"] > 0:
                    valid_products.append(p)
            except:
                continue

        if not valid_products:
            return {"message": "No valid prices found", "results": []}

        min_price = min(p["price_value"] for p in valid_products)
        min_delivery = min(p.get("delivery_days", 4) for p in valid_products)

        for p in valid_products:
            p["score"] = round(
                (p.get("rating", 3.5) / 5) * 0.4 +
                (min_price / p["price_value"]) * 0.4 +
                (min_delivery / p.get("delivery_days", 4)) * 0.2,
                3
            )

        best = max(valid_products, key=lambda x: x["score"])
        others = [p for p in valid_products if p is not best]

        return {
            "message": "Found best deal",
            "results": [{
                "product_name": best["name"],
                "brand": "N/A",
                "best_deal": best,
                "other_offers": others
            }]
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"message": str(e), "results": []}



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
