import asyncio
import logging
import time
from threading import Lock

from app.core.config import get_settings
from app.connectors.registry import get_active_connectors
from app.scrapers.amazon import search_amazon
from app.scrapers.flipkart import search_flipkart
from app.scrapers.myntra import search_myntra
from app.scrapers.ajio import search_ajio

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Search response cache.
#
# search_all() / search_with_marketplaces() cache successful (non-empty)
# results per normalized query so that repeated / equivalent searches
# short-circuit the expensive live browser pipeline.  A shallow copy of the
# cached payload (products + marketplace summary) is returned so callers can
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
    """Return a cached outcome dict (shallow copies) or None on miss/expiry."""
    settings = get_settings()
    if not settings.search_cache_enabled:
        return None

    with _search_cache_lock:
        entry = _search_cache.get(key)
        if not entry:
            return None
        stamp, outcome = entry
        if time.monotonic() - stamp > settings.search_cache_ttl_seconds:
            _search_cache.pop(key, None)
            return None
        return {
            "products": list(outcome["products"]),
            "marketplaces": [dict(m) for m in outcome["marketplaces"]],
        }


def _cache_store(key, outcome):
    """Store a successful (non-empty) outcome dict {products, marketplaces}."""
    settings = get_settings()
    if not settings.search_cache_enabled:
        return
    with _search_cache_lock:
        _search_cache[key] = (time.monotonic(), outcome)


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
# Source registry (markets as first-class connectors).
#
# Every marketplace is described by a MarketplaceConnector (key, display name,
# retrieval kind) backed by a search_<source> callable that conforms to the
# protocol documented in app/scrapers/protocol.py.  The connector list is
# declared in app/connectors/registry.py; callables are resolved dynamically
# from THIS module's attributes so monkeypatching in tests keeps working.
#
# Which sources are ACTIVE (and which retrieval kind each uses) is decided by
# the live <key>_data_source settings — see app/connectors/base.py.  The
# registry answers get_active_connectors() from those settings at call time,
# so enabling/disabling a marketplace never requires editing this module.
#
# To add a new e-commerce source:
#   1. Create app/scrapers/<source>.py with a search_<source>(query) -> list[dict]
#   2. Declare its data source in app/core/config.py
#   3. Append a MarketplaceConnector to app/connectors/registry.py
# ---------------------------------------------------------------------------


def _resolve_sources():
    """Resolve [(connector, callable), ...] from this module's attributes.

    Resolving at call time (rather than caching at import time) ensures that
    monkeypatching in tests takes effect and that a marketplace disabled via
    its data-source setting is simply not part of the run.
    """
    return [
        (connector, connector.resolve())
        for connector in get_active_connectors()
    ]


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


# ---------------------------------------------------------------------------
# Catalog (persisted-offers) integration.
#
# The catalog turns the API into a comparison platform that accumulates real
# observed offers over time.  It fails open: any catalog lookup or write error
# (missing data dir, corrupted file, disk full) merely degrades the pipeline
# to today's live-only behaviour and never fails a search.
# ---------------------------------------------------------------------------

def _catalog_enabled() -> bool:
    """True when persistence is switched on (defensive vs test settings)."""
    return bool(getattr(get_settings(), "catalog_enabled", True))


def _stored_search_offers(key):
    """Stored (previously observed) offers for *key* when fresh, else None.

    Serves cached real offers WITHOUT re-scraping -- and, unlike the in-memory
    cache, it survives restarts/redeploys -- while the stored snapshot is
    younger than search_cache_ttl_seconds (bounded by the explicit
    stored_search_freshness_seconds cap).  Honest empty semantics are
    preserved: a query with no stored offers still runs the live pipeline, and
    disabling the search cache disables stored serving too.
    """
    settings = get_settings()
    if not _catalog_enabled() or not getattr(settings, "search_cache_enabled", True):
        return None
    try:
        from app.storage.store import get_store
        cache_ttl = float(getattr(settings, "search_cache_ttl_seconds", 300.0))
        stored_freshness = float(
            getattr(settings, "stored_search_freshness_seconds", 86400.0)
        )
        freshness = min(cache_ttl, stored_freshness)
        stored = get_store().search_offers(key, max_age_seconds=freshness)
    except Exception as e:
        logger.warning("Catalog lookup failed: %r", e)
        return None
    if stored:
        logger.info("Serving %d stored offers for '%s'", len(stored), key)
        return stored
    return None


def _persist_results(query_key, query, all_products, marketplaces):
    """Best-effort persistence of a fresh non-empty search into the catalog."""
    if not _catalog_enabled() or not all_products:
        return
    try:
        from app.storage.store import get_store
        get_store().upsert_search_results(
            query_key,
            query,
            all_products,
            source_updates=[
                {
                    "key": m["key"],
                    "display_name": m["display_name"],
                    "kind": m["kind"],
                    "ok": m["ok"],
                }
                for m in marketplaces
            ],
        )
    except Exception as e:
        logger.warning("Catalog persistence failed: %r", e)


# Display name -> connector key used to derive summaries for previously-stored
# offers (the in-memory/catalog paths), where only offer-shaped data survives.
_PLATFORM_TO_KEY = {
    "Amazon": "amazon",
    "Flipkart": "flipkart",
    "Myntra": "myntra",
    "Ajio": "ajio",
}


def _marketplaces_from_products(products):
    """Derive an honest marketplace summary from a list of real offers.

    Used when serving previously-stored (catalog) offers: only marketplaces
    that actually appear in the real offers are listed; every entry reports
    its real offer count and ok=true.  kind is empty because the retrieval
    kind is not preserved in the stored offer shape.
    """
    counts = {}
    for p in products or []:
        platform = (p or {}).get("platform")
        if not platform:
            continue
        counts[platform] = counts.get(platform, 0) + 1
    return [
        {
            "key": _PLATFORM_TO_KEY.get(platform, platform.lower()),
            "display_name": platform,
            "kind": "",
            "offer_count": count,
            "ok": True,
        }
        for platform, count in sorted(counts.items())
    ]


async def search_all(query: str):
    """Run the pipeline and return ONLY the collected products (list[dict]).

    Kept as the familiar list-returning entry point.  The marketplace summary
    is computed inside the same single pipeline run; callers that need it use
    search_with_marketplaces().
    """
    outcome = await _search_run(query)
    return outcome["products"]


async def search_with_marketplaces(query: str):
    """Run the pipeline and return {"products": [...], "marketplaces": [...]}.

    `marketplaces` is built from the ACTUAL connector execution for this query:
    one entry per source that ran, reporting the real offer count and ok
    status.  It is never manufactured, never implies offers from a source that
    did not return any, and never mentions a marketplace that is not part of
    the run (e.g. a disabled one).
    """
    return await _search_run(query)


async def _search_run(query: str) -> dict:
    """The single pipeline behind search_all() / search_with_marketplaces()."""

    logger.info("Searching for: %s", query)

    key = _normalized_cache_key(query)
    cached = _cache_lookup(key)
    if cached is not None:
        logger.info("Cache hit for '%s' (%d products)", key, len(cached["products"]))
        return cached

    stored = _stored_search_offers(key)
    if stored is not None:
        return {
            "products": stored,
            "marketplaces": _marketplaces_from_products(stored),
        }

    coalesce_map = _get_coalesce_map()
    in_flight = coalesce_map.get(key)
    if in_flight is not None and not in_flight.done():
        # An identical search is already running.  Share its outcome instead
        # of opening a second scrape pipeline / consuming a concurrency slot.
        logger.info("Coalescing into in-flight search for '%s'", key)
        outcome = await in_flight
        return outcome

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
            f"{connector.display_name}: {len(items)}"
            for (connector, _), items in zip(sources, results)
        ]
        logger.info("Platform results — %s", ", ".join(source_counts))

        all_products = []
        for items in results:
            all_products.extend(items)

        marketplaces = [
            {
                "key": connector.key,
                "display_name": connector.display_name,
                "kind": connector.active_kind,
                "offer_count": len(items),
                "ok": bool(items),
            }
            for (connector, _), items in zip(sources, results)
        ]

        logger.info("Total products collected: %d", len(all_products))

        outcome = {
            "products": all_products,
            "marketplaces": marketplaces,
        }

        if all_products:
            _cache_store(key, outcome)
            _persist_results(key, query, all_products, marketplaces)

        if not future.done():
            future.set_result(outcome)
        return outcome
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
