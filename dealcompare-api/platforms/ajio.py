from urllib.parse import quote_plus


def search_ajio(query: str):

    encoded = quote_plus(query)
    url = f"https://www.ajio.com/search/?text={encoded}"

    product = {
        "title": query.title(),
        "platform": "Ajio",
        "price_value": 0,
        "price_display": "Check price",
        "rating": None,
        "url": url,
        "image": ""
    }

    return [product]