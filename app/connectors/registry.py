"""Default marketplace connectors wired into the DealCompare search pipeline.

The `attr` name is the search_<source> callable on app.services.search_service
(imported at call time), so monkeypatching in tests continues to work.
"""

from app.connectors.base import MarketplaceConnector

DEFAULT_CONNECTORS = [
    MarketplaceConnector("amazon", "Amazon", "scrape", "search_amazon"),
    MarketplaceConnector("flipkart", "Flipkart", "scrape", "search_flipkart"),
    MarketplaceConnector("myntra", "Myntra", "http", "search_myntra"),
    MarketplaceConnector("ajio", "Ajio", "scrape", "search_ajio"),
]