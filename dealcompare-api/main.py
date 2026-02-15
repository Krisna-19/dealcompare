from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.search_service import search_all

from services.grouping_service import group_products
from services.aggregation_service import aggregate_grouped_products

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
    try:
        amazon = search_amazon(query)
        myntra = search_myntra(query)
        ajio = search_ajio(query)

        all_products = amazon + myntra + ajio

        if not all_products:
            return {
                "message": "No products found",
                "results": []
            }

        grouped = group_products(all_products)
        aggregated = aggregate_grouped_products(grouped)

        return {
            "message": "Products compared successfully",
            "results": aggregated
        }

    except Exception as e:
        return {"error": str(e)}
