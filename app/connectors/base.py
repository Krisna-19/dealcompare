"""
Marketplace connector abstraction.

A connector is an inspectable handle to one marketplace data source,
describing HOW it is queried (official API / HTTP feed / browser scrape)
while delegating the actual retrieval to the existing search_<source>
functions.  Connectors make the source registry in search_service declarative
and give the catalog store the metadata (key / display name / kind) it needs
to record marketplace health.

IMPORTANT (test compatibility): retrieval is resolved dynamically at call
time from the search_service module (connector.attr), so the established test
pattern of monkeypatching `search_service.search_amazon` keeps working
unchanged.
"""

from __future__ import annotations

from typing import Callable


class MarketplaceConnector:
    """One marketplace source contracted to return DealCompare offer dicts."""

    def __init__(self, key: str, display_name: str, kind: str, attr: str):
        self.key = key
        self.display_name = display_name
        self.kind = kind          # "api" | "http" | "scrape"
        self.attr = attr          # module attribute resolving to search_<name>

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