from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.aggregator import aggregate_products
from platforms.amazon import search_amazon
from platforms.myntra import search_myntra
from platforms.ajio import search_ajio

from services.search_service import search_all
from services.ranking_service import score_product

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/search")
def search(query: str):
    results = []

    amazon_products = search_amazon(query)
    myntra_products = search_myntra(query)
    ajio_products = search_ajio(query)

    results.extend(amazon_products)
    results.extend(myntra_products)
    results.extend(ajio_products)
    try:
        products = search_all(query)
        ranked = rank_products(products)
        return {"results": ranked}
    except Exception as e:
        print("ERROR:", e)
        return {"error": str(e)}


    if not results:
        return {
            "message": "No products found",
            "results": []
        }

    aggregated = aggregate_products(results)

    return {
        "message": "Products aggregated successfully",
        "results": aggregated
    }
