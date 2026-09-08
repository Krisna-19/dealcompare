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


# ---------------------------------------------------------------------------
# Global scrape-concurrency control + per-source timeout.
#
# Scraping spawns real Chromium sessions (app/scrapers/*).  Without a global
# gate, a traffic spike can open an unbounded number of browsers at once, and
# one slow marketplace can stall an entire /search response.  Two guards cover
# both in this module:
#
#   1. scrape_concurrency_limit  – an asyncio.Semaphore shared by every source
#      of every in-flight request caps simultaneous browser sessions per
#      process.  asyncio.Semaphore is bound to its event loop, and a module
#      instance created at import time would be tied to whatever loop (if any)
#      was running then; production uvicorn has exactly one loop, but tests
#      spin up a fresh loop per asyncio.run() call.  So one semaphore is
#      cached per running loop.
#
#   2. source_timeout_seconds    – each source runs under a deadline.  On
#      expiry the source is abandoned (honest empty [] for that source) so the
#      response never waits on it.  The underlying worker thread keeps running
#      in the background; its concurrency slot is held until it truly finishes
#      so the browser-session cap is never exceeded by aborted scrapes.
#
# Success/failure contract is unchanged: sources still return [] on any
# failure, empty/failed searches are never cached, and only genuinely found
# products reach the response.
# ---------------------------------------------------------------------------

_scrape_semaphore_lock = Lock()
_scrape_semaphores = {}  # running event loop -> asyncio.Semaphore


def _get_scrape_semaphore() -> asyncio.Semaphore:
    """Return the loop-scoped semaphore capping scrape concurrency."""
    settings = get_settings()
    limit = max(1, getattr(settings, "scrape_concurrency_limit", 2))
    loop = asyncio.get_running_loop()
    with _scrape_semaphore_lock:
        semaphore = _scrape_semaphores.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(limit)
            _scrape_semaphores[loop] = semaphore
        return semaphore


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
# In-flight request coalescing.
#
# While a /search for a given normalized query is still running, a second
# identical request should NOT start its own scrape pipeline (each of which
# contends for a concurrency slot and spawns Chromium).  Instead it attaches
# to the already-running pipeline and awaits the same outcome.
#
# Implementation: one dict per running event loop mapping normalized key ->
# asyncio.Future.  The map is strictly bounded: an entry exists only while a
# search for that query is genuinely in flight, and is always removed when the
# pipeline finishes (success, empty, or raised).  This is NOT a result cache —
# the persistent TTL cache above still decides whether a *completed* search is
# reused; coalescing only collapses identical requests that overlap in time.
# ---------------------------------------------------------------------------

_coalesce_lock = Lock()
_coalesce_map = {}  # running loop -> {normalized_key -> asyncio.Future}


def _get_coalesce_map():
    """Return the in-flight map for the current event loop.

    Loop-scoped (like the semaphore) so production's single uvicorn loop holds
    one map while tests, which spin up a fresh loop per asyncio.run() call, are
    isolated from one another.  Entries for already-dead loops are pruned so
    recycled loops never leak stale futures.
    """
    loop = asyncio.get_running_loop()
    with _coalesce_lock:
        dead = [l for l in _coalesce_map if l.is_closed()]
        for l in dead:
            _coalesce_map.pop(l, None)
        return _coalesce_map.setdefault(loop, {})


def clear_coalesce_map():
    """Drop every in-flight coalescing entry (used by tests)."""
    with _coalesce_lock:
        _coalesce_map.clear()

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

    coalesce_map = _get_coalesce_map()
    in_flight = coalesce_map.get(key)
    if in_flight is not None and not in_flight.done():
        # An identical search is already running.  Share its outcome instead
        # of opening a second scrape pipeline / consuming a concurrency slot.
        logger.info("Coalescing into in-flight search for '%s'", key)
        return await in_flight

    # Check-and-insert happens synchronously (no await between the cache
    # lookup above and the gather below), so two tasks cannot both miss and
    # start a second pipeline for the same key on one event loop.
    future = asyncio.get_running_loop().create_future()
    coalesce_map[key] = future

    try:
        sources = _resolve_sources()
        semaphore = _get_scrape_semaphore()

        results = await asyncio.gather(
            *(_run_source_in_thread(fn, query, semaphore) for _, fn in sources)
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

        if not future.done():
            future.set_result(all_products)
        return all_products
    except Exception as e:
        if not future.done():
            future.set_exception(e)
        raise
    finally:
        # Drop this key whether the pipeline produced results, returned empty,
        # or raised, so the coalescing map stays bounded and a later identical
        # request starts fresh (and, if it succeeded, hits the TTL cache).
        if coalesce_map.get(key) is future:
            del coalesce_map[key]


def _release_when_done(task, semaphore):
    """Release *semaphore* exactly once, after *task* truly finishes.

    A source abandoned by timeout keeps running in its worker thread; holding
    its slot until completion keeps the global browser-session cap exact even
    though the response has already moved on.
    """
    async def _reaper():
        try:
            await task
        except Exception:
            pass
        finally:
            semaphore.release()

    try:
        asyncio.get_running_loop().create_task(_reaper())
    except RuntimeError:
        # Loop shutting down mid-request: no-one is waiting on the slot any
        # more, so drop it now rather than never.
        semaphore.release()


async def _run_source_in_thread(source, query, semaphore):
    """Run a source callable under the global concurrency cap and a deadline.

    A source that exceeds the deadline returns [] (honest empty for that
    source) instead of stalling the whole /search response.
    """
    settings = get_settings()
    timeout = getattr(settings, "source_timeout_seconds", 60.0)

    await semaphore.acquire()

    task = asyncio.create_task(asyncio.to_thread(_run_source, source, query))

    released = False
    try:
        done, _pending = await asyncio.wait(
            {task},
            timeout=(timeout if timeout and timeout > 0 else None),
        )
        if task in done:
            semaphore.release()
            released = True
            return task.result()
    finally:
        if not released:
            if task.done():
                semaphore.release()
            else:
                _release_when_done(task, semaphore)

    name = getattr(source, "__name__", repr(source))
    logger.warning(
        "Source %s exceeded %.1fs timeout; returning honest empty",
        name,
        timeout,
    )
    return []
