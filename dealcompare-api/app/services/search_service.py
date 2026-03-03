from app.scrapers.amazon import search_amazon
from app.scrapers.myntra import search_myntra
from app.scrapers.ajio import search_ajio
import asyncio

async def search_all(query: str):

            amazon_task = search_amazon(query)
            myntra_task = asyncio.to_thread(search_myntra, query)
            ajio_task = asyncio.to_thread(search_ajio, query)

            results = await asyncio.gather(
                amazon_task,
                myntra_task,
                ajio_task,
                return_exceptions=True
            )

            all_products = []

            for result in results:
                if isinstance(result, list):
                    all_products.extend(result)

            return all_products