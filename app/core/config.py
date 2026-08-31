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
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
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

    # --- CORS ---------------------------------------------------------------
    # Comma-separated origin allow-list. Defaults keep local Vite dev servers
    # working plus the production site; "*" is discouraged (use only if you
    # fully understand the implications).
    allowed_origins: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:5500,"
        "http://127.0.0.1:5500,"
        "https://dealcompare.in"
    )

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
