from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.search_service import search_all
from services.ranking_service import rank_products

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

    products = search_all(query)

    if not products:
        return {"message": "Product not found", "results": []}

    ranked = rank_products(products)

    return {
        "message": "Products found",
        "results": [p.to_dict() for p in ranked]
    }
