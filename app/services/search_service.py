import asyncio
import logging
import sys
import time
from threading import Lock

from app.core.config import get_settings
from app.scrapers.amazon import search_amazon
from app.scrapers.flipkart import search_flipkart
from app.scrapers.myntra import search_myntra
from app.scrapers.ajio import search_ajio

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Search response cache.
#
# search_all() caches successful (non-empty) results per normalized query so
# that repeated / equivalent searches short-circuit the expensive live browser
# pipeline.  A shallow copy of the cached list is returned so callers can
# never corrupt the shared entry.
#
# Failure contract is preserved: only genuinely successful (non-empty) results
# are cached.  Empty results and scraper failures are honestly re-run on the
# next call, so a temporarily-degraded marketplace can never be served a stale
# blank answer.  See app/core/config.py for the TTL / enabled switches.
# ---------------------------------------------------------------------------

_search_cache = {}
_search_cache_lock = Lock()


def _normalized_cache_key(query: str) -> str:
    """A stable cache key: case-folded and whitespace-collapsed query."""
    return " ".join((query or "").strip().lower().split())


def _cache_lookup(key):
    """Return a cached result list (shallow copy) or None on miss/expiry."""
    settings = get_settings()
    if not settings.search_cache_enabled:
        return None

    with _search_cache_lock:
        entry = _search_cache.get(key)
        if not entry:
            return None
        stamp, results = entry
        if time.monotonic() - stamp > settings.search_cache_ttl_seconds:
            _search_cache.pop(key, None)
            return None
        return list(results)


def _cache_store(key, results):
    """Store a successful (non-empty) result list for *key*."""
    settings = get_settings()
    if not settings.search_cache_enabled:
        return
    with _search_cache_lock:
        _search_cache[key] = (time.monotonic(), results)


def clear_search_cache():
    """Drop every cached search result (used by tests)."""
    with _search_cache_lock:
        _search_cache.clear()

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

    key = _normalized_cache_key(query)
    cached = _cache_lookup(key)
    if cached is not None:
        logger.info("Cache hit for '%s' (%d products)", key, len(cached))
        return cached

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

    if all_products:
        _cache_store(key, all_products)

    return all_products


async def _run_source_in_thread(source, query):
    """Run a source callable in a thread with error isolation."""
    return await asyncio.to_thread(_run_source, source, query)
