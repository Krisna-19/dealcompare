from urllib.parse import quote_plus
from app.utils.text_utils import generate_product_key

def search_myntra(query):

    results = []

    products = [
        {
            "title": query.title(),
            "url": f"https://www.myntra.com/{query.replace(' ', '')}"
        }
    ]

    for product in products:

        title = product["title"]

        product_key = generate_product_key(title)

        if not product_key:
            continue

        results.append({
            "title": title,
            "product_key": product_key,
            "platform": "Myntra",
            "price_value": 0,
            "price_display": "Check price",
            "url": product["url"]
        })

    return results