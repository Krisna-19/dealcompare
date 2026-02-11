from typing import List
from models.product_model import Product
from services.ranking_service import score_product

AMAZON_TAG = "dealcompare19-21"

def build_amazon_search_url(query: str) -> str:
    q = query.replace(" ", "+")
    return f"https://www.amazon.in/s?k={q}&tag={AMAZON_TAG}"


def fetch_amazon_products(query: str) -> List[Product]:
    base_url = build_amazon_search_url(query)

    products = []

    for i in range(5):
        products.append(
            Product(
                title=f"{query.title()} - Option {i+1}",
                platform="Amazon",
                price_display="Check price",
                price_value=0,
                rating=None,
                image="",
                url=base_url,
                category="General",
                score=score_product(i),
            )
        )

    return products
