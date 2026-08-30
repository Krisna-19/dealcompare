from urllib.parse import quote_plus
from app.utils.text_utils import generate_product_key


def search_ajio(query: str):

    results = []

    encoded = quote_plus(query)
    url = f"https://www.ajio.com/search/?text={encoded}"

    title = query.title()

    product_key = generate_product_key(title)

    if not product_key:
        return []

    results.append({
        "title": title,
        "product_key": product_key,
        "platform": "Ajio",
        "price_value": 0,
        "price_display": "Check price",
        "url": url,
        "image": ""
    })

    return results