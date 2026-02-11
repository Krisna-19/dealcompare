from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from services.search_service import fetch_amazon_products
import re

app = FastAPI(title="DealCompare API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@app.get("/search")
def search(query: str = Query(...)):
    query = normalize(query)

    if not query:
        return {"message": "Invalid query", "results": []}

    products = fetch_amazon_products(query)

    if not products:
        return {"message": "No products found", "results": []}

    return {
        "message": "Top matching products found",
        "results": [p.__dict__ for p in products]
    }
