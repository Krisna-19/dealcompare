from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.search_service import search_all

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
        results = search_all(query)

        if not results:
            return {
                "message": "No products found",
                "results": []
            }

        return {
            "message": "Products fetched successfully",
            "results": results
        }

    except Exception as e:
        print("ERROR:", e)
        return {"error": str(e)}
