"""
Central definition of the API error contract.

Every error response uses FastAPI's standard envelope with a structured,
human-safe detail object and NO internal information:

    {
        "detail": {
            "error": "<stable machine-readable code>",
            "message": "<safe, user-facing message>"
        }
    }

Status-code policy:
    200  success            -> {"message": "Products compared successfully", "results": [...]}
    200  honest empty       -> {"message": "No products found", "results": []}
    422  invalid_query      -> missing / blank / whitespace-only 'query' parameter
    502  upstream_scrape_failed -> product-source pipeline failed (not a fake result)
    500  internal_error     -> any unexpected backend exception (details logged
                                server-side only, never in the response)
"""

from fastapi import HTTPException

# Stable machine-readable error codes
ERROR_INVALID_QUERY = "invalid_query"
ERROR_UPSTREAM_SCRAPE_FAILED = "upstream_scrape_failed"
ERROR_INTERNAL = "internal_error"


def http_error(status_code: int, code: str, message: str) -> HTTPException:
    """Build an HTTPException carrying the structured error contract."""
    return HTTPException(
        status_code=status_code,
        detail={"error": code, "message": message},
    )
