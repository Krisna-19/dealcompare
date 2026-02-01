import os
import re
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

STOP_WORDS = {
    "for", "with", "and", "or", "of", "the",
    "men", "mens", "women", "womens",
    "tshirt", "t-shirt", "shirt"
}

def normalize(text: str) -> list[str]:
    text = re.sub(r"[^a-z0-9 ]", "", text.lower())
    words = text.split()
    return [w for w in words if w not in STOP_WORDS]


def simplify_query(query: str) -> str:
    words = normalize(query).split()
    return " ".join(words[:3])

def smart_match_score(product_name: str, query: str) -> float:
    q_words = set(normalize(query))
    p_words = set(normalize(product_name))

    if not q_words or not p_words:
        return 0

    # 🔹 keyword overlap
    overlap = len(q_words & p_words) / len(q_words)

    # 🔹 name similarity
    name_score = SequenceMatcher(
        None,
        " ".join(q_words),
        " ".join(p_words)
    ).ratio()

    # 🔹 brand boost
    q_brand = extract_brand(query)
    p_brand = extract_brand(product_name)

    brand_boost = 0.2 if q_brand and q_brand == p_brand else 0

    # 🔹 final weighted score
    return round(
        (overlap * 0.5) +
        (name_score * 0.3) +
        brand_boost,
        3
    )


def extract_brand(text: str) -> str | None:
    known_brands = ["levis", "nike", "adidas", "puma", "roadster"]
    text = text.lower()
    for b in known_brands:
        if b in text:
            return b
    return None

def pick_best_product(products: list, query: str, min_score: float = 0.55):
    best = None
    best_score = 0

    for p in products:
        score = smart_match_score(p.get("name", ""), query)

        if score > best_score:
            best = p
            best_score = score
        print("MATCH:", p["name"], score)
    

    if best_score < min_score:
        return None

    best["match_score"] = best_score
    return best


def parse_price(price: str) -> int:
    try:
        return int(price.replace("₹", "").replace(",", ""))
    except:
        return 0

def ensure_price_value(products: list):
    for p in products:
        if "price_value" not in p:
            p["price_value"] = parse_price(p.get("price", "0"))
    return products


# --------------------------------------------------
# Routes
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
        return {"message": "No query", "results": []}

    q = query.strip()
    scrape_q = simplify_query(q)
    offers = []

    # ---------- MYNTRA ----------
    try:
        myntra_products = scrape_myntra(scrape_q)
        best = pick_best_product(myntra_products, q)
        if best:
            best["platform"] = "Myntra"
            best["price_value"] = parse_price(best.get("price", "0"))
            offers.append(best)
    except Exception as e:
        print("Myntra error:", e)

    # ---------- FLIPKART ----------
    try:
        flipkart_products = scrape_flipkart(scrape_q)
        best = pick_best_product(flipkart_products, q)
        if best:
            best["platform"] = "Flipkart"
            best["price_value"] = parse_price(best.get("price", "0"))
            offers.append(best)
    except Exception as e:
        print("Flipkart error:", e)

    # ---------- SEED FALLBACK ----------
    if not offers:
        norm_q = normalize(q)
        for k, v in SEED_PRODUCTS.items():
            if k in norm_q:
                offers = ensure_price_value(v)
                break

    if not offers:
        return {"message": "No deals found", "results": []}

    # ---------- BEST DEAL ----------
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


# --------------------------------------------------
# Run
# --------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
