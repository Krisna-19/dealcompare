import re
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Query
from typing import Optional
import os
import uvicorn

app = FastAPI(title="DealCompare API")

# ✅ SINGLE CORS middleware (keep only one)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- NORMALIZE FUNCTION ----------------
def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]', '', text)  # remove spaces, hyphens, symbols
    return text


# ---------------- SEARCH API ----------------
@app.get("/search")
def search(query: Optional[str] = Query(None)):
    filtered = PRODUCTS

    if query:
        q = normalize(query)   # ✅ FIX: normalize query too

        filtered = [
            p for p in PRODUCTS
            if q in normalize(p["name"])
            or q in normalize(p["brand"])
            or q in normalize(p["category"])
        ]

    groups = {}
    for p in filtered:
        key = (p["name"], p["brand"])
        groups.setdefault(key, []).append(p)

    results = []
    for (name, brand), offers in groups.items():
        def price(p): 
            return int(p["price"].replace("₹", "").replace(",", ""))

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



# ---------------- SUGGEST API ----------------
@app.get("/suggest")
def suggest(query: str):
    q = normalize(query)
    suggestions = []

    for p in PRODUCTS:
        if q in normalize(p["name"]):
            suggestions.append(p["name"])

    return list(dict.fromkeys(suggestions))[:5]


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
