from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.services.search_service import search_all
from app.aggregator.aggregator import aggregate_products
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/search")
async def search(query: str):

        try:
            products = await search_all(query)

            compared = aggregate_products(products)

            return {
                "message": "Products compared successfully",
                "results": compared
            }

        except Exception as e:
            return {"error": str(e)}
