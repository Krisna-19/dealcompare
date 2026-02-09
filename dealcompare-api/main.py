import os
import re
import time
from typing import Optional, List

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from scrapers.myntra import scrape_myntra
from scrapers.ajio import scrape_ajio
from affiliates.amazon_links import build_amazon_search_link


app = FastAPI(title="DealCompare API")

# =========================
# CONFIG
# =========================
CACHE = {}
CACHE_TTL = 300  # 5 minutes


# =========================
# CORS
# =========================
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


# =========================
# HELPERS
# =========================
def is_valid_product(p: dict) -> bool:
    """
    Accept only real product entries
    """
    price = p.get("price_value", 0)
    url = p.get("product_url", "")

    if price <= 0:
        return False

    if not url or "search" in url:
        return False

    return True

def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def price_value(price: str) -> int:
    try:
        return int(price.replace("₹", "").replace(",", "").strip())
    except:
        return 0


def pick_best_per_site(products: List[dict]) -> List[dict]:
    """
    Pick ONE best product per platform (lowest price)
    """
    best = {}

    for p in products:
        platform = p.get("platform")
        if not platform:
            continue

        p["price_value"] = price_value(p.get("price", "0"))

        if platform not in best or p["price_value"] < best[platform]["price_value"]:
            best[platform] = p

    return list(best.values())


def score_product(product: dict) -> float:
    """
    Safe relevance score:
    - Missing rating → assume 3.5
    - Missing price → penalize
    """
    price = product.get("price_value")
    rating = product.get("rating")

    # Normalize rating
    if rating is None or not isinstance(rating, (int, float)):
        rating = 3.5

    # Normalize price
    if price is None or price <= 0:
        price = 999999  # penalize unknown price

    return (rating * 2) - (price / 1000)


# =========================
# ROUTES
# =========================
@app.get("/")
def root():
    return {"status": "DealCompare API running"}


@app.get("/search")
def search(query: Optional[str] = Query(None)):
    if not query:
        return {"message": "No query", "results": []}

    q = normalize(query)
    now = time.time()

    # ---- CACHE ----
    if q in CACHE and now - CACHE[q]["time"] < CACHE_TTL:
        return CACHE[q]["data"]

    all_products = []

    # ---- SCRAPING ----
    try:
        all_products.extend(scrape_myntra(q))
    except Exception as e:
        print("Myntra error:", e)

    try:
        all_products.extend(scrape_ajio(q))
    except Exception as e:
        print("Ajio error:", e)

    # ---- NO PRODUCTS FOUND ----
    if not all_products:
        return {
            "message": "Product not found on supported platforms",
            "results": []
        }

    # ---- PICK BEST PER SITE ----
    # ---- PICK BEST PER SITE ----
    per_site = pick_best_per_site(all_products)

    # ---- FILTER INVALID PRODUCTS ----
    per_site = [p for p in per_site if is_valid_product(p)]

    if not per_site:
        return {
            "message": "No valid products found",
            "results": []
        }

    


    # ---- SCORE & SORT ----
    for p in per_site:
        p["score"] = score_product(p)

    per_site.sort(key=lambda x: x["score"], reverse=True)

    # ---- TOP 3 PRODUCTS ----
    top_products = per_site[:3]

    results = []
    for p in top_products:
        results.append({
            "product_name": p.get("name"),
            "best_deal": p,
            "other_offers": [],
            "amazon_affiliate_url": build_amazon_search_link(query)
        })

    response = {
        "message": "Top matching products found",
        "results": results
    }

    CACHE[q] = {
        "time": now,
        "data": response
    }

    return response


# =========================
# RUN
# =========================
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
