from platforms import amazon, myntra, ajio

def search_all(query: str):

    products = []

    products.extend(amazon.search(query))
    products.extend(myntra.search(query))
    products.extend(ajio.search(query))

    return products
