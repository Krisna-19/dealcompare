from models.product_model import Product
from utils.category import detect_category
from urllib.parse import quote_plus

def search_amazon(query: str):
    return [
        {
            "title": query.title(),
            "price_value": 0.0,
            "price_display": "Check price",
            "platform": "Amazon",
            "url": f"https://www.amazon.in/s?k={query.replace(' ', '+')}&tag=dealcompare19-21",
            "rating": None,
            "image": ""
        }
    ]
