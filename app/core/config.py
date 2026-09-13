"""
Central, environment-backed application settings.

Values default to the previously hardcoded ones so behaviour is unchanged
when no environment variables are set. Override any of them via environment
variables (see .env.example) or a local .env file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Source scraping -------------------------------------------------
    amazon_base_url: str = "https://www.amazon.in"
    flipkart_base_url: str = "https://www.flipkart.com"
    myntra_base_url: str = "https://www.myntra.com"
    ajio_base_url: str = "https://www.ajio.com"
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    # Headless is the recommended/default production configuration: servers
    # have no display, and a visible browser wastes resources on a deployment.
    # Set HEADLESS_BROWSER=false only for local, visible-browser debugging.
    headless_browser: bool = True
    page_load_timeout_ms: int = 60000
    selector_timeout_ms: int = 20000
    max_results_per_platform: int = 8
    match_score_threshold: int = 10

    # --- HTTP client (utils/http_client.py) ------------------------------
    http_user_agent: str | None = None          # falls back to user_agent
    http_accept_language: str = "en-IN,en;q=0.9"
    http_max_retries: int = 3
    http_backoff_factor: float = 1.0
    http_timeout_seconds: float = 8.0
    # Comma-separated proxy URLs; empty means direct connection only.
    http_proxies: str = ""

    # --- Grouping / ranking ----------------------------------------------
    group_similarity_threshold: float = 0.6

    # --- Search cache ------------------------------------------------------
    # Repeated/identical queries short-circuit the live browser scrape
    # pipeline for search_cache_ttl_seconds.  Only successful (non-empty)
    # results are cached; empty/failed searches are never cached.
    search_cache_enabled: bool = True
    search_cache_ttl_seconds: float = 300.0

    # --- Product catalog persistence ----------------------------------------
    # Buyhatke-style foundation: persist normalized offers (canonical
    # products, offers, price history, marketplace health, per-query search
    # index) to a restart-safe JSON store (app/storage/store.py).  Set
    # CATALOG_DATA_DIR / DEALCOMPARE_DATA_DIR to a persistent disk so the
    # catalog survives restarts and redeploys.  The store fails open: any
    # catalog error degrades the pipeline to today's live-only behaviour.
    catalog_enabled: bool = True
    catalog_data_dir: str = "./data"
    # While younger than this many seconds, stored offers for a query are
    # served WITHOUT re-scraping (fast, stable, marketplace-consistent).
    stored_search_freshness_seconds: float = 86400.0
    # Per-offer price-history depth kept in the catalog.
    price_history_limit: int = 50

    # --- Production hardening ------------------------------------------------
    # Global cap on simultaneous browser/scrape sessions across ALL in-flight
    # requests (per process).  Prevents the API from spawning unlimited
    # Chromium instances when traffic spikes.
    scrape_concurrency_limit: int = 2
    # Per-source wall-clock deadline while scraping.  A marketplace that
    # exceeds this is abandoned for that response (honest empty for that
    # source only) so one slow/stuck scraper can never stall /search.
    source_timeout_seconds: float = 60.0

    # --- Optional per-IP rate limiting ---------------------------------------
    # In-memory sliding-window limiter applied to incoming requests by client
    # IP.  Off by default because it never adds correctness, only protection;
    # enable it only when a reverse proxy supplies real client IPs (this app
    # deliberately does not trust X-Forwarded-For headers).
    rate_limit_enabled: bool = False
    rate_limit_max_requests: int = 60
    rate_limit_window_seconds: float = 60.0

    # --- Affiliates --------------------------------------------------------
    affiliate_base_url: str = "https://www.amazon.in"
    amazon_affiliate_tag: str = "dealcompare19-21"
    # Optional tags for the other platforms.  When empty, offers from that
    # platform are returned with their original (untagged) URL.
    flipkart_affiliate_tag: str = ""
    myntra_affiliate_tag: str = ""
    ajio_affiliate_tag: str = ""

    # --- Marketplace data-source selection ------------------------------------
    # Per-marketplace selector controlling which retrieval path the connector
    # routes to.  The connector registry (app/connectors/*) reads these at
    # call time: a marketplace whose source is "disabled" is dropped from the
    # active source list entirely (deferred), never called, and never reported.
    #
    #   amazon      "scraper" (default) | "api"          - Creators API adapter
    #   flipkart    "scraper" (default) | "api"          - Affiliate API (with
    #               scraper fallback, unchanged legacy behaviour)
    #   myntra      "http" (default)    | "scraper"      - "http" is the
    #               browser-free honest-empty path; "scraper" preserves the
    #               legacy HTTP-primary + Playwright-fallback behaviour
    #   ajio        "scraper" (default) | "disabled"     - "disabled" defers the
    #               source (honest empty) with no browser/network attempt
    amazon_data_source: str = "scraper"
    flipkart_data_source: str = "scraper"
    myntra_data_source: str = "http"
    ajio_data_source: str = "scraper"

    # --- Flipkart Affiliate API -----------------------------------------------
    # Optional official Flipkart Affiliate search API (affiliate.flipkart.com).
    # Enabled only when FLIPKART_DATA_SOURCE=api AND both credentials below are
    # non-empty; otherwise the existing Playwright scraper is used unchanged.
    # (The FLIPKART_DATA_SOURCE toggle itself lives in the data-source section
    # above; it is kept duplicated there for the connector registry.)
    # Affiliate Tracking ID (e.g. "abc-21").  Keep empty in non-API mode.
    flipkart_affiliate_id: str = ""
    # Affiliate API Token issued on affiliate.flipkart.com.  Keep empty in
    # non-API mode.  Never commit a real token to source control.
    flipkart_affiliate_token: str = ""
    # Base URL of the official Affiliate search API (v1.0 JSON).
    flipkart_api_base_url: str = (
        "https://affiliate-api.flipkart.net/affiliate/1.0"
    )
    # Number of results to request from the search API.  The documented API
    # maximum is 10 and there is no pagination for search.
    flipkart_api_result_count: int = 10
    # API request timeout in seconds.
    flipkart_api_timeout_seconds: float = 8.0

    # --- Amazon Creators API --------------------------------------------------
    # Official Amazon Creators API (the successor to the Product Advertising
    # API 5, deprecated 2026-05-15): creatorsapi.amazon.  Enabled only when
    # AMAZON_DATA_SOURCE=api AND the three credentials/partner tag below are
    # non-empty; otherwise the adapter fails safe with honest empty and never
    # falls back to the old Playwright scraper while "api" is selected.
    # Never commit real credentials to source control.
    amazon_creator_client_id: str = ""
    amazon_creator_client_secret: str = ""
    amazon_partner_tag: str = ""
    # Storefront the Creators API is queried against.  Keep the full host so
    # the x-marketplace header and detailPageURL base stay aligned.
    amazon_marketplace: str = "www.amazon.in"
    amazon_creators_api_base_url: str = "https://creatorsapi.amazon"
    # OAuth2 LwA token endpoint.  India (IN) is served by the EU regional
    # endpoint (region 3.2) — overrideable when Amazon moves regions around.
    amazon_creators_token_url: str = "https://api.amazon.co.uk/auth/o2/token"
    # Token request scopes-granted: the Creators API default scope.
    amazon_creators_scope: str = "creatorsapi::default"
    amazon_creators_timeout_seconds: float = 8.0
    # Number of items requested per SearchItems call (capped downstream by
    # max_results_per_platform).
    amazon_creators_result_count: int = 10

    # --- CORS ---------------------------------------------------------------
    # Comma-separated origin allow-list. Defaults keep local Vite dev servers
    # working plus the production site; "*" is discouraged (use only if you
    # fully understand the implications).
    allowed_origins: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:5500,"
        "http://127.0.0.1:5500,"
        "https://dealcompare.in,"
        "https://dealcompare.onrender.com"
    )

    # --- Observability ---------------------------------------------------------
    # Root logger level. Startup applies this to the root logger after the
    # default INFO basicConfig (see app/main.py).
    log_level: str = "INFO"
    # Expose /metrics (Prometheus text format). Disabling it also skips the
    # per-request instrumentation work in the metrics middleware.
    metrics_enabled: bool = True

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def http_proxies_list(self) -> list[str | None]:
        proxies = [p.strip() for p in self.http_proxies.split(",") if p.strip()]
        return proxies or [None]  # direct connection when unset


@lru_cache
def get_settings() -> Settings:
    return Settings()
