import os
import re
import time
from difflib import SequenceMatcher
from collections import defaultdict
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from scrapers.flipkart import scrape_flipkart
from scrapers.myntra import scrape_myntra
from affiliates.amazon_links import build_amazon_search_link
from seed_data import SEED_PRODUCTS

# ==================================================
# APP
# ==================================================

app = FastAPI(title="DealCompare API")

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

CACHE = {}
CACHE_TTL = 300  # 5 minutes

# ==================================================
# HELPERS
# ==================================================

STOP_WORDS = {
    "for", "with", "and", "or", "of", "the",
    "men", "mens", "women", "womens",
    "tshirt", "t-shirt", "shirt"
}

BRANDS = ["levis", "nike", "adidas", "puma", "roadster", "apple", "samsung"]

def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()

def tokenize(text: str) -> list:
    return [w for w in normalize(text).split() if w not in STOP_WORDS]

def simplify_query(query: str) -> str:
    return " ".join(tokenize(query)[:3])

def extract_brand(text: str):
    t = normalize(text)
    for b in BRANDS:
        if b in t:
            return b
    return None

def parse_price(price: str) -> int:
    try:
        return int(price.replace("₹", "").replace(",", ""))
    except:
        return 0

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def smart_match_score(product_name: str, query: str) -> float:
    q_words = set(tokenize(query))
    p_words = set(tokenize(product_name))

    if not q_words or not p_words:
        return 0

    overlap = len(q_words & p_words) / len(q_words)
    name_score = similarity(" ".join(q_words), " ".join(p_words))

    brand_boost = 0.2 if extract_brand(query) == extract_brand(product_name) else 0

    return round(overlap * 0.5 + name_score * 0.3 + brand_boost, 3)

def build_myntra_search_link(query: str) -> str:
    return f"https://www.myntra.com/search?q={query.replace(' ', '+')}"

def build_ajio_search_link(query: str) -> str:
    return f"https://www.ajio.com/search/?text={query.replace(' ', '+')}"

# ==================================================
# ROUTES
# ==================================================

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
    nq = normalize(q)
    now = time.time()

    # ---------- CACHE ----------
    if nq in CACHE and now - CACHE[nq]["time"] < CACHE_TTL:
        return CACHE[nq]["data"]

    scrape_q = simplify_query(q)
    all_products = []

    # ---------- SCRAPE ----------
    try:
        all_products.extend(scrape_myntra(scrape_q))
    except:
        pass

    try:
        all_products.extend(scrape_flipkart(scrape_q))
    except:
        pass

    # ---------- FALLBACK ----------
    if not all_products:
        for k, v in SEED_PRODUCTS.items():
            if k in nq:
                all_products = v
                break

    if not all_products:
        return {"message": "No products found", "results": []}

    # ---------- SCORE ----------
    scored = []
    for p in all_products:
        try:
            p["price_value"] = parse_price(p.get("price", "0"))
            p["match_score"] = smart_match_score(p.get("name", ""), q)
            scored.append(p)
        except:
            continue

    scored.sort(key=lambda x: x["match_score"], reverse=True)

    # ---------- PICK TOP 3 PRODUCTS ----------
    grouped = defaultdict(list)
    for p in scored:
        grouped[p["name"]].append(p)
        if len(grouped) == 3:
            break

    results = []

    for product_name, offers in grouped.items():
        offers.sort(key=lambda x: x["price_value"])
        best = offers[0]
        others = offers[1:]

        # ---------- FIX BAD URLS ----------
        for p in offers:
            url = p.get("product_url", "")
            if p.get("platform") == "Myntra" and url.endswith(".com"):
                p["product_url"] = build_myntra_search_link(q)
            if p.get("platform") == "Ajio" and url.endswith(".com"):
                p["product_url"] = build_ajio_search_link(q)

        results.append({
            "product_name": product_name,
            "brand": extract_brand(product_name) or "N/A",
            "match_confidence": best["match_score"],
            "best_deal": best,
            "other_offers": others,
            "amazon_affiliate_url": build_amazon_search_link(product_name),
        })

    response = {
        "message": "Top matching products found",
        "results": results,
    }

    CACHE[nq] = {"time": now, "data": response}
    return response

# ==================================================
# RUN
# ==================================================

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
