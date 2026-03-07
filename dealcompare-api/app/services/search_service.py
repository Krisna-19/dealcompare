import asyncio

from app.scrapers.amazon import search_amazon
from app.scrapers.myntra import search_myntra
from app.scrapers.ajio import search_ajio


async def search_all(query: str):

    print(f"\n🔎 Searching for: {query}")

    amazon_task = asyncio.to_thread(search_amazon, query)
    myntra_task = asyncio.to_thread(search_myntra, query)
    ajio_task = asyncio.to_thread(search_ajio, query)

    results = await asyncio.gather(
        amazon_task,
        myntra_task,
        ajio_task
    )

    amazon_products = results[0]
    myntra_products = results[1]
    ajio_products = results[2]

    print("Amazon results:", len(amazon_products))
    print("Myntra results:", len(myntra_products))
    print("Ajio results:", len(ajio_products))

    all_products = []
    for r in results:
        all_products.extend(r)

    print("Total products collected:", len(all_products))

    return all_products