import asyncio

from app.scrapers.amazon import search_amazon
from app.scrapers.myntra import search_myntra
from app.scrapers.ajio import search_ajio


async def search_all(query: str):

    amazon_task = asyncio.to_thread(search_amazon, query)
    myntra_task = asyncio.to_thread(search_myntra, query)
    ajio_task = asyncio.to_thread(search_ajio, query)

    results = await asyncio.gather(
        amazon_task,
        myntra_task,
        ajio_task
    )

    all_products = []
    for r in results:
        all_products.extend(r)

    return all_products