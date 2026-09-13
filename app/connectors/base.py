"""
Marketplace connector abstraction.

A connector is an inspectable handle to one marketplace data source,
describing HOW it is queried (official API / HTTP feed / browser scrape)
while delegating the actual retrieval to the existing search_<source>
functions.  Connectors make the source registry in search_service declarative
and give the catalog store the metadata (key / display name / kind) it needs
to record marketplace health.

Data-source routing (Phase F): each marketplace has a live
`<key>_data_source` setting (see app/core/config.py).  The connector exposes
it as `.data_source`, maps it to the *runtime* kind via `.active_kind`
("api" / "http" / "scrape" / "deferred") and honours "disabled" through
`.enabled` — a disabled marketplace is never resolved, never called and never
reported.  The `.kind` attribute stays the *declared* kind (used by the
catalog health records when the connector is active).

IMPORTANT (test compatibility): retrieval is resolved dynamically at call
time from the search_service module (connector.attr), so the established test
pattern of monkeypatching `search_service.search_amazon` keeps working
unchanged.
"""

from __future__ import annotations

from typing import Callable

from app.core.config import get_settings


def _active_kind_for(data_source: str) -> str:
    """Map a data-source value onto the runtime connector kind."""
    source = (data_source or "").strip().lower()
    if source == "disabled":
        return "deferred"
    if source == "api":
        return "api"
    if source == "http":
        return "http"
    return "scrape"


class MarketplaceConnector:
    """One marketplace source contracted to return DealCompare offer dicts."""

    def __init__(self, key: str, display_name: str, kind: str, attr: str):
        self.key = key
        self.display_name = display_name
        self.kind = kind          # declared: "api" | "http" | "scrape"
        self.attr = attr          # module attribute resolving to search_<name>

    @property
    def data_source(self) -> str:
        """Live `<key>_data_source` setting for this marketplace."""
        return str(
            getattr(get_settings(), f"{self.key}_data_source", "scraper")
        ).strip().lower() or "scraper"

    @property
    def active_kind(self) -> str:
        """Runtime kind derived from the live data source configuration."""
        return _active_kind_for(self.data_source)

    @property
    def enabled(self) -> bool:
        """A 'disabled' marketplace is deferred (not part of the pipeline)."""
        return self.data_source != "disabled"

    def run(self, query: str) -> list:
        """Run the source for *query* -> list[dict] (honest-empty on failure)."""
        fn = self.resolve()
        if fn is None:
            return []
        return fn(query)

    def resolve(self) -> Callable:
        """The callable backing this connector (resolved from search_service)."""
        from app.services import search_service as mod
        return getattr(mod, self.attr, None)

    def __repr__(self):  # pragma: no cover - debug aid
        return (
            f"MarketplaceConnector(key={self.key!r}, display_name="
            f"{self.display_name!r}, kind={self.kind!r}, attr={self.attr!r})"
        )


def iter_default_connectors():
    """Yield every connector wired into the search pipeline."""
    from app.connectors.registry import DEFAULT_CONNECTORS
    yield from DEFAULT_CONNECTORS