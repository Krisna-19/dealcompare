from platforms.amazon import search_amazon
from platforms.myntra import search_myntra
from platforms.ajio import search_ajio


def search_all(query: str):

    products = []

    try:
        products.extend(search_amazon(query))
    except Exception as e:
        print("Amazon error:", e)

    try:
        products.extend(search_myntra(query))
    except Exception as e:
        print("Myntra error:", e)

    try:
        products.extend(search_ajio(query))
    except Exception as e:
        print("Ajio error:", e)

    return products
