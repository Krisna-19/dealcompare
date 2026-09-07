"""
Per-request correlation: one request id per /search invocation.

The id lives in a module-level ContextVar instead of being threaded through
function signatures, so the sync scrapers -- which run inside
asyncio.to_thread() workers -- inherit it automatically and no scraper
callable needs to change.  A logging.Filter attached to the root logger stamps
every emitted record with the active id:

    app.scrapers.flipkart: [request_id=abc] Flipkart returned: 8 results
    app.services.search_service: [request_id=abc] Platform results - Flipkart: 8

so scraper results can be correlated with the aggregated platform counts of
the same request.  Lines emitted outside any /search request carry ``-``.
"""

import logging
from contextvars import ContextVar
from uuid import uuid4

#: Attribute name the filter attaches to each LogRecord.
_ATTR = "request_id"

#: Default keeps log lines well-formed when no request is active.
request_id_var: ContextVar[str] = ContextVar(_ATTR, default="-")


def new_request_id() -> str:
    """A short, URL-safe id for one logical /search request."""
    return uuid4().hex[:12]


class RequestIdFilter(logging.Filter):
    """Stamp each record with the active request id (or ``-`` when unset)."""

    def filter(self, record: logging.LogRecord) -> bool:
        setattr(record, _ATTR, request_id_var.get())
        return True