import asyncio
import logging
import sys

from app.scrapers.amazon import search_amazon
from app.scrapers.flipkart import search_flipkart
from app.scrapers.myntra import search_myntra
from app.scrapers.ajio import search_ajio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source registry.
#
# To add a new e-commerce source:
#   1. Create app/scrapers/<source>.py with a search_<source>(query) -> list[dict]
#   2. Import it above
#   3. Append ("Display Name", "search_<name>") to _SOURCE_REGISTRY below
#
# Each callable must conform to the protocol documented in
# app/scrapers/protocol.py.
# ---------------------------------------------------------------------------
_SOURCE_REGISTRY = [
    ("Amazon", "search_amazon"),
    ("Flipkart", "search_flipkart"),
    ("Myntra", "search_myntra"),
    ("Ajio", "search_ajio"),
]


def _resolve_sources():
    """Resolve (name, callable) pairs from this module's current attributes.

    Resolving at call time (rather than caching at import time) ensures that
    monkeypatching in tests takes effect.
    """
    mod = sys.modules[__name__]
    return [(name, getattr(mod, attr)) for name, attr in _SOURCE_REGISTRY]


def _run_source(source, query):
    """
    Run a single source, catching any unexpected exception so that one
    broken source never prevents the others from returning results.
    """
    try:
        return source(query)
    except Exception as e:
        logger.error("Source %s failed: %r", getattr(source, "__name__", source), e)
        return []


async def search_all(query: str):

    logger.info("Searching for: %s", query)

    sources = _resolve_sources()

    results = await asyncio.gather(
        *(_run_source_in_thread(fn, query) for _, fn in sources)
    )

    source_counts = [
        f"{name}: {len(items)}"
        for (name, _), items in zip(sources, results)
    ]
    logger.info("Platform results — %s", ", ".join(source_counts))

    all_products = []
    for items in results:
        all_products.extend(items)

    logger.info("Total products collected: %d", len(all_products))

    return all_products


async def _run_source_in_thread(source, query):
    """Run a source callable in a thread with error isolation."""
    return await asyncio.to_thread(_run_source, source, query)
