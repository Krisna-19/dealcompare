from urllib.parse import quote_plus


def search_myntra(query: str):

    encoded = quote_plus(query)
    url = f"https://www.myntra.com/{encoded}"

    product = {
        "title": query.title(),
        "platform": "Myntra",
        "price_value": 0,
        "price_display": "Check price",
        "rating": None,
        "url": url,
        "image": ""
    }

    return [product]