"""
In-flight request coalescing in app/services/search_service.py.

When two identical /search queries overlap in time, only one scrape pipeline
should run; the second request awaits and shares the first's outcome instead of
opening its own pipeline (and competing for a concurrency slot).

Tests exercise single-loop scenarios (matching production's one uvicorn loop)
by scheduling multiple search_all() calls concurrently inside one event loop.
"""

import asyncio
import time

from app.services import search_service


def _loop_run(coro):
    """Run *coro* on a fresh single event loop (asyncio.run handles setup and
    cleanup of the loop and its tasks)."""
    return asyncio.run(coro)


def _stub_others_empty(monkeypatch):
    monkeypatch.setattr(search_service, "search_flipkart", lambda q: [])
    monkeypatch.setattr(search_service, "search_myntra", lambda q: [])
    monkeypatch.setattr(search_service, "search_ajio", lambda q: [])


def test_concurrent_identical_queries_run_one_pipeline(monkeypatch, make_product):
    """Two overlapping identical searches share a single scrape pipeline."""
    real = make_product()
    calls = {"n": 0}

    def amazon(q):
        calls["n"] += 1
        time.sleep(0.05)  # keep the pipeline in flight so both calls overlap
        return [real]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    async def run_both():
        return await asyncio.gather(
            search_service.search_all("iphone 15"),
            search_service.search_all("iphone 15"),
        )

    a, b = _loop_run(run_both())

    assert a == [real]
    assert b == [real]
    # Only ONE scrape pipeline ran despite two concurrent requests.
    assert calls["n"] == 1


def test_concurrent_identical_queries_share_the_same_result(monkeypatch, make_product):
    """Both overlapping callers receive the exact same result object."""
    real = make_product()
    calls = {"n": 0}

    def amazon(q):
        calls["n"] += 1
        time.sleep(0.05)
        return [real]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    async def run_both():
        return await asyncio.gather(
            search_service.search_all("iphone 15"),
            search_service.search_all("iphone 15"),
        )

    a, b = _loop_run(run_both())

    assert calls["n"] == 1
    assert a == b == [real]


def test_normalized_equivalent_queries_coalesce(monkeypatch, make_product):
    """'iPhone   15  ' and 'iphone 15' normalize to one key -> one pipeline."""
    real = make_product()
    calls = []

    def amazon(q):
        calls.append(q)
        time.sleep(0.05)
        return [real]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    async def run_both():
        return await asyncio.gather(
            search_service.search_all("  iPhone   15 "),
            search_service.search_all("iphone 15"),
        )

    a, b = _loop_run(run_both())

    assert calls == ["  iPhone   15 "]  # only the first (verbatim) query ran
    assert a == b == [real]


def test_distinct_queries_do_not_coalesce(monkeypatch, make_product):
    """Different queries each run their own pipeline."""
    calls = []

    def amazon(q):
        calls.append(q)
        return [make_product(title=f"{q} product")]

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    async def run_both():
        return await asyncio.gather(
            search_service.search_all("iphone"),
            search_service.search_all("samsung"),
        )

    a, b = _loop_run(run_both())

    assert calls == ["iphone", "samsung"]
    assert a != b


def test_coalesced_pipeline_failure_is_shared_and_cleaned_up(monkeypatch, make_product):
    """On pipeline failure, waiters share the failure and the entry is removed.

    The pipeline yields first (so the second caller attaches to it), then the
    scrape raises.  The attached waiter observes the same failure, and the
    coalescing entry is removed so a later identical request starts fresh.
    """
    real = make_product()

    async def flaky_source(source, query, semaphore):
        # Let the first pipeline reach the in-flight point (so the second
        # caller attaches), then fail the pipeline from inside the gather.
        await asyncio.sleep(0.05)
        raise RuntimeError("pipeline failure")

    default_run = search_service._run_source_in_thread
    monkeypatch.setattr(search_service, "_run_source_in_thread", flaky_source)
    monkeypatch.setattr(search_service, "search_amazon", lambda q: [real])
    _stub_others_empty(monkeypatch)

    # Run the coalesced-failure and the recovery on the SAME loop so we verify
    # the coalescing entry is genuinely removed after the failure (not just
    # that a fresh loop has an empty map).
    async def scenario():
        first, second = await asyncio.gather(
            search_service.search_all("q"),
            search_service.search_all("q"),
            return_exceptions=True,
        )
        # Restore a healthy pipeline, then confirm a later identical request
        # is not stuck on a stale failed future and re-runs successfully.
        monkeypatch.setattr(search_service, "_run_source_in_thread", default_run)
        recovered = await search_service.search_all("q")
        return first, second, recovered

    first, second, recovered = _loop_run(scenario())

    # The first caller raised, and the attached waiter observed the failure.
    assert isinstance(first, RuntimeError)
    assert isinstance(second, RuntimeError)

    # Cleanup must have dropped the entry: a fresh request re-runs and succeeds.
    assert recovered == [real]


def test_coalesced_empty_result_is_shared_and_cleaned_up(monkeypatch):
    """Honest-empty results are shared by waiters, and NOT cached.

    Both callers get [] and the coalescing entry is removed (so the next call
    re-runs, since empty results are never cached).
    """
    calls = {"n": 0}

    def amazon(q):
        calls["n"] += 1
        time.sleep(0.05)
        return []

    monkeypatch.setattr(search_service, "search_amazon", amazon)
    _stub_others_empty(monkeypatch)

    async def scenario():
        a, b = await asyncio.gather(
            search_service.search_all("q"),
            search_service.search_all("q"),
        )
        after_coalesce = calls["n"]
        # Same loop: a later call (still uncached) must run a fresh pipeline.
        later = await search_service.search_all("q")
        after_fresh = calls["n"]
        return a, b, later, after_coalesce, after_fresh

    a, b, later, after_coalesce, after_fresh = _loop_run(scenario())

    assert a == b == []
    assert after_coalesce == 1  # one pipeline for two overlapping empties
    assert later == []          # the recovered/fresh call ran (2nd pipeline)
    assert after_fresh == 2
