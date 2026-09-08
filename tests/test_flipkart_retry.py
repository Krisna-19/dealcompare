"""
Bounded empty-result retry in app/scrapers/flipkart.py.

_search_flipkart_scraper() must retry AT MOST once, and only when the first
Playwright scrape comes back empty.  A hard page-load failure on the first
attempt must NOT be retried.  Every path is bounded (max 2 scraper invocations),
so there is no possibility of an infinite retry loop.

The retry lives in _search_flipkart_scraper() (exercised here) which is the
entry point reached from search_flipkart() after the Affiliate-API dispatch.
"""

import app.scrapers.flipkart as flipkart


def _stub_scrape(monkeypatch, outcomes):
    """Replace _scrape_flipkart with a queue of outcomes.

    outcomes: list of either a list (returned) or an Exception instance
    (raised, simulating a hard browser/page failure).
    """
    calls = {"n": 0}

    def fake_scrape(query, url):
        idx = calls["n"]
        calls["n"] += 1
        outcome = outcomes[min(idx, len(outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(flipkart, "_scrape_flipkart", fake_scrape)
    return calls


def test_nonempty_first_attempt_does_not_retry(monkeypatch, make_product):
    real = make_product(platform="Flipkart", title="Shirt")
    calls = _stub_scrape(monkeypatch, [[real, real]])

    results = flipkart._search_flipkart_scraper("shirt")

    assert results == [real, real]
    assert calls["n"] == 1  # only the first scrape; no retry on non-empty


def test_empty_first_attempt_retries_once_and_returns_second(monkeypatch, make_product):
    real = make_product(platform="Flipkart", title="Shirt")
    calls = _stub_scrape(monkeypatch, [[], [real]])

    results = flipkart._search_flipkart_scraper("shirt")

    assert results == [real]
    assert calls["n"] == 2  # empty first attempt triggered the single retry


def test_double_empty_attempts_return_empty_after_two(monkeypatch):
    calls = _stub_scrape(monkeypatch, [[], []])

    results = flipkart._search_flipkart_scraper("shirt")

    assert results == []
    assert calls["n"] == 2  # both attempts ran, still empty


def test_hard_failure_on_first_attempt_is_not_retried(monkeypatch):
    calls = _stub_scrape(monkeypatch, [TimeoutError("page.goto timeout")])

    results = flipkart._search_flipkart_scraper("shirt")

    assert results == []
    assert calls["n"] == 1  # a hard load failure must NOT be retried


def test_empty_then_hard_failure_returns_empty_after_retry(monkeypatch):
    calls = _stub_scrape(monkeypatch, [[], TimeoutError("second goto")])

    results = flipkart._search_flipkart_scraper("shirt")

    assert results == []
    assert calls["n"] == 2  # empty first -> one retry -> retry raised -> empty


def test_retry_is_bounded_to_one(monkeypatch):
    """Even with a perpetually-empty scraper, we never retry more than once."""
    calls = _stub_scrape(monkeypatch, [[], []])

    flipkart._search_flipkart_scraper("shirt")

    # Two invocations total, no third attempt -> bounded, no infinite loop.
    assert calls["n"] == 2
