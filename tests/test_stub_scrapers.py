from app.scrapers.ajio import search_ajio


def test_ajio_stub_returns_no_results():
    assert search_ajio("iphone 15") == []
    assert search_ajio("kurti") == []
    assert search_ajio("") == []


def test_ajio_stub_can_never_emit_priced_entries():
    """
    Regression guard: if someone reintroduces fabricated offers into the
    Ajio stub, this test fails unless every emitted entry carries a real
    price.  (Myntra is now a real scraper and is covered by its own tests.)
    """
    results = search_ajio("iphone 15")
    assert isinstance(results, list)
    assert results == [], (
        f"{search_ajio.__name__} must return an empty list; "
        f"got {len(results)} entries"
    )
    for entry in results:
        assert isinstance(entry, dict)
        assert entry.get("price_value", 0) > 0
        assert entry.get("price_display") not in (None, "", "Check price")
