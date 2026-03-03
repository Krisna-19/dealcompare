from platforms.amazon import search_amazon
from platforms.myntra import search_myntra
from platforms.ajio import search_ajio

def search_all(query: str):

    print("search_all triggered")
    print("Calling Amazon...")

    amazon_products = search_amazon(query)

    print("Amazon returned:", len(amazon_products))

    print("Calling Myntra...")
    myntra_products = search_myntra(query)
    print("Myntra returned:", len(myntra_products))

    print("Calling Ajio...")
    ajio_products = search_ajio(query)
    print("Ajio returned:", len(ajio_products))

    all_products = amazon_products + myntra_products + ajio_products

    print("Total products collected:", len(all_products))

    return all_products
