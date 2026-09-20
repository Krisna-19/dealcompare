"""
CLI entry point for merchant-feed ingestion.

    python -m app.feed --source <merchant> --file <path> [--query-key <key>]

Reads a JSON/CSV feed file, normalizes and ingests it into the DealCompare
catalog, and prints an honest summary (rows / accepted / rejected).  CLI only:
this intentionally does not expose a public HTTP ingestion endpoint, and it
never reads or prints credentials -- feeds are supplied by partners, not
scraped.
"""

from __future__ import annotations

import argparse
import sys

from app.feed.importer import ingest_feed
from app.feed.parser import read_feed_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.feed",
        description="Ingest a merchant product feed (JSON/CSV) into the DealCompare catalog.",
    )
    parser.add_argument(
        "--source", required=True,
        help="Merchant/feed identifier (also recorded as the offer provenance).",
    )
    parser.add_argument(
        "--file", required=True,
        help="Path to the feed file (.json or .csv).",
    )
    parser.add_argument(
        "--query-key", default=None,
        help="Optional normalized query to also associate the offers with "
             "(adds a search_index entry; omitted by default).",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    rows = read_feed_file(args.file)
    result = ingest_feed(args.source, rows, query_key=args.query_key)

    print(f"feed ingestion complete: source={result.source}")
    print(f"rows     : {result.rows}")
    print(f"accepted : {result.accepted}")
    print(f"rejected : {result.rejected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())