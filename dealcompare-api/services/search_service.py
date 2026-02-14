from platforms import amazon, myntra, ajio

def search_all(query: str):

    results = []

    results += amazon.search(query)
    results += myntra.search(query)
    results += ajio.search(query)

    return results
