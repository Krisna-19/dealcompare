from models.product_model import Product
from utils.category import detect_category
from urllib.parse import quote_plus

def search_myntra(query: str):

    category = detect_category(query)
    encoded = quote_plus(query)

    url = f"https://www.myntra.com/{encoded}"

    product = Product(
        title=query.title(),
        platform="Myntra",
        price_value=0,
        price_display="Check price",
        rating=None,
        url=url,
        image=""
    )

    return [product]
