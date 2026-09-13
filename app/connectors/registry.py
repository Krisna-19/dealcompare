"""Default marketplace connectors wired into the DealCompare search pipeline.

The `attr` name is the search_<source> callable on app.services.search_service
(imported at call time), so monkeypatching in tests continues to work.

Active-source resolution (Phase F): the source each connector actually uses is
decided by the live `<key>_data_source` setting (app/core/config.py), NOT by
editing this list or search_service.  get_active_connectors() drops any
marketplace whose source is "disabled" (deferred / honest empty) so the
pipeline, catalog health and logs simply never hear about it.

To add a new e-commerce source:
  1. Create app/scrapers/<source>.py with a search_<source>(query) -> list[dict]
  2. Declare its data source in app/core/config.py (<source>_data_source)
  3. Append a MarketplaceConnector below
  4. (Optional) add a <source>_data_source block to .env.example
"""

from app.connectors.base import MarketplaceConnector

DEFAULT_CONNECTORS = [
    MarketplaceConnector("amazon", "Amazon", "scrape", "search_amazon"),
    MarketplaceConnector("flipkart", "Flipkart", "scrape", "search_flipkart"),
    MarketplaceConnector("myntra", "Myntra", "http", "search_myntra"),
    MarketplaceConnector("ajio", "Ajio", "scrape", "search_ajio"),
]


def get_active_connectors():
    """The connectors whose marketplaces are NOT configured as deferred.

    Filtering happens against live settings at call time, so flipping a
    `*_DATA_SOURCE` environment variable changes the active source set
    without any code or registry change.
    """
    return [connector for connector in DEFAULT_CONNECTORS if connector.enabled]