from app.scrapers.ajio import search_ajio


def test_ajio_search_returns_a_list_without_raising():
    """
    Ajio is now a real scraper (no longer a stub).  It must return a list and
    never raise, whether Ajio is unreachable (Akamai anti-bot HTTP 403 ->
    honest empty []) or reachable (real offers).
    """
    results = search_ajio("iphone 15")
    assert isinstance(results, list)
    results2 = search_ajio("kurti")
    assert isinstance(results2, list)


def test_ajio_never_emits_unpriced_or_fabricated_entries():
    """
    Honest-data guard: any entry Ajio ever returns must be a real, priced,
    Ajio-hosted offer.  If someone reintroduces fabricated offers this guard
    fails.  The list may be empty (when Ajio's anti-bot blocks the scraper) or
    full of real offers (when Ajio is reachable); the guard is invariant.
    """
    results = search_ajio("iphone 15")
    assert isinstance(results, list)
    for entry in results:
        assert isinstance(entry, dict)
        assert entry.get("platform") == "Ajio"
        assert entry.get("price_value", 0) > 0
        assert entry.get("price_display") not in (None, "", "Check price")
        assert isinstance(entry.get("title"), str) and entry["title"].strip()
        assert str(entry.get("url", "")).startswith("https://www.ajio.com/")
