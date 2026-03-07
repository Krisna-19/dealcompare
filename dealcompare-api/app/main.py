from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.services.search_service import search_all
from app.aggregator.aggregator import aggregate_products


app = FastAPI(
    title="DealCompare API",
    description="Product price comparison engine",
    version="1.0"
)

# CORS (for frontend connection)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "DealCompare API running 🚀"}


@app.get("/search")
async def search(query: str):

        try:
            products = await search_all(query)

            if not products:
                return {
                    "message": "No products found",
                    "results": []
                }

            compared = aggregate_products(products)

            return {
                "message": "Products compared successfully",
                "results": compared
            }

        except Exception as e:
            return {"error": str(e)}