"""
DealCompare merchant-feed ingestion (Phase 9).

A legitimate merchant/API can hand DealCompare a product feed (JSON or CSV).
The feed is parsed into generic rows (app/feed/parser.py), normalized onto the
existing DealCompare offer contract reusing app/scrapers/contract.py
(app/feed/normalizer.py), and persisted through the existing catalog store
(app/feed/importer.py -> app/storage/store.py).  No marketplace scraper,
connector, or search behavior is touched; feeds are an opt-in, source-agnostic
supply of offers.

Invocation (CLI only, no public HTTP endpoint):
    python -m app.feed --source <merchant> --file <path> [--query-key <key>]
"""

from app.feed.importer import IngestResult, ingest_feed
from app.feed.normalizer import normalize_record

__all__ = ["IngestResult", "ingest_feed", "normalize_record"]