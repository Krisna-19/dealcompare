import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import (
    ERROR_INTERNAL,
    ERROR_INVALID_QUERY,
    ERROR_RATE_LIMITED,
    ERROR_UPSTREAM_SCRAPE_FAILED,
    http_error,
)
from app.services.search_service import search_all
from app.services.ranking_service import filter_irrelevant_products
from app.aggregator.aggregator import aggregate_products
from app.services.affiliate_service import enrich_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="DealCompare API",
    description="Product price comparison engine",
    version="1.0"
)

# CORS: explicit origin allow-list from settings (ALLOWED_ORIGINS).
# The app is stateless (no cookies/auth), so credentials stay disabled;
# combining allow_credentials=True with a wildcard origin is invalid per
# the CORS specification.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "DealCompare API running 🚀"}


@app.get("/health")
def health():
    """Liveness probe for load balancers / orchestrators.

    Deliberately dependency-free: the process is healthy iff it can answer.
    This endpoint is exempt from the optional per-IP rate limiter so monitoring
    traffic never trips protection meant for real clients.
    """
    return {"status": "ok"}


# -----------------------------------------------------------------------------
# Optional per-IP rate limiting.
#
# A minimal in-memory sliding-window limiter using only the standard library
# (deque of timestamps per client IP).  It is OFF by default; enable it via
# RATE_LIMIT_ENABLED=true when a reverse proxy supplies real client IPs.  This
# app deliberately never trusts X-Forwarded-For, so enabling it behind a proxy
# that does not overwrite that header would rate-limit the proxy's IP, not the
# client.  Rejects with the standard error contract at 429.
# -----------------------------------------------------------------------------

_rate_limit_history: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def per_ip_rate_limit(request: Request, call_next):
    settings = get_settings()

    if settings.rate_limit_enabled:
        if request.url.path == "/health":
            # Monitoring/liveness traffic bypasses the quota (still served).
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = settings.rate_limit_window_seconds
        limit = settings.rate_limit_max_requests

        if limit > 0:
            history = _rate_limit_history[client_ip]
            while history and now - history[0] > window:
                history.popleft()

            if len(history) >= limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": {
                            "error": ERROR_RATE_LIMITED,
                            "message": "Too many requests. Please try again later.",
                        }
                    },
                )

            history.append(now)

    return await call_next(request)


@app.get("/search")
async def search(query: str = Query(...)):

    q = query.strip()
    if not q:
        # Client error: nothing meaningful to search for.
        raise http_error(
            422,
            ERROR_INVALID_QUERY,
            "Query parameter 'query' must contain at least one non-whitespace character.",
        )

    try:
        products = await search_all(q)
    except Exception as e:
        # Upstream/pipeline failure: report honestly as a server-side
        # upstream problem, never as fabricated or empty "success" data.
        logger.error("Upstream scrape failure for query '%s': %r", q, e)
        raise http_error(
            502,
            ERROR_UPSTREAM_SCRAPE_FAILED,
            "Product sources are temporarily unavailable. Please try again shortly.",
        )

    if not products:
        # Honest empty result: genuinely no products found.
        return {
            "message": "No products found",
            "results": []
        }

    products = filter_irrelevant_products(products, q)

    if not products:
        return {
            "message": "No products found",
            "results": []
        }

    try:
        compared = aggregate_products(products)
    except Exception as e:
        logger.error("Unexpected aggregation failure for query '%s': %r", q, e)
        raise http_error(
            500,
            ERROR_INTERNAL,
            "An unexpected internal error occurred while processing results.",
        )

    # Add affiliate tags to offer urls purely at the response boundary.  This
    # runs AFTER aggregation so grouping/dedup/best-price were computed on the
    # original urls; it never changes card identity, prices, or offer shape.
    compared = enrich_results(compared)

    return {
        "message": "Products compared successfully",
        "results": compared
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Final safety net for any exception that escapes an endpoint.

    Returns a generic 500 with the standard error contract. Internal
    details, stack traces, and exception text stay on the server.
    """
    logger.error("Unhandled error on %s: %r", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "error": ERROR_INTERNAL,
                "message": "An unexpected internal error occurred.",
            }
        },
    )