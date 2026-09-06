import { useState } from "react";
import {
  STORES,
  SORT_MODES,
  filterByStore,
  sortProducts,
  cardOffers,
  bestVisibleOffer,
} from "../lib/filterSort";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

/* The free-tier backend can take ~110s (Amazon source timeout + Playwright
   scrapes). Timeout above that worst case so a slow-but-alive search is never
   aborted early, and add one retry to ride out a cold-start connection drop. */
const SEARCH_TIMEOUT_MS = 140000;

function fetchWithTimeout(url, timeoutMs = SEARCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { signal: controller.signal }).finally(() => clearTimeout(timer));
}

/* CATEGORY → ICON MAP */
const CATEGORY_ICONS = {
  Fashion: "👕",
  Electronics: "💻",
  Beauty: "🧴",
  General: "🛒",
};

const toNumber = (value) => {
  if (value === null || value === undefined || value === "") return NaN;
  return Number(value);
};

function cheapestIndexes(offers) {
  const numeric = offers.map((offer) => toNumber(offer.price_value));
  const finite = numeric.filter(Number.isFinite);
  if (finite.length === 0) return new Set();

  const min = Math.min(...finite);
  const set = new Set();
  numeric.forEach((value, index) => {
    if (Number.isFinite(value) && value === min) set.add(index);
  });
  return set;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState([]);
  const [category, setCategory] = useState("General");
  const [activeStore, setActiveStore] = useState("All Stores");
  const [sortMode, setSortMode] = useState("best-deal");

  const searchDeals = async (event) => {
    event.preventDefault();

    const trimmed = query.trim();
    if (!trimmed) return;

    setLoading(true);
    setError("");
    setResults([]);
    setActiveStore("All Stores");
    setSortMode("best-deal");

    try {
      let res = null;
      try {
        res = await fetchWithTimeout(
          `${API_BASE}/search?query=${encodeURIComponent(trimmed)}`
        );
      } catch {
        // One retry: the first attempt may be dropped during the free-tier
        // cold start; the retry hits a warm instance and typically succeeds.
        res = await fetchWithTimeout(
          `${API_BASE}/search?query=${encodeURIComponent(trimmed)}`
        );
      }

      if (!res.ok) throw new Error("API error");

      const data = await res.json();

      if (data.results && data.results.length > 0) {
        setResults(data.results);
        setCategory(data.category || "General");
      } else {
        setError("No products found");
      }
    } catch {
      setError("Failed to fetch deals");
    } finally {
      setLoading(false);
    }
  };

  const filtered = filterByStore(results, activeStore);
  const visible = sortProducts(filtered, sortMode, activeStore);

  return (
    <div className="container">
      {/* HEADER */}
      <h1 className="title">
        DealCompare <span role="img" aria-label="fire">🔥</span>
      </h1>
      <p className="subtitle">Compare prices across multiple platforms</p>

      {/* SEARCH */}
      <form className="search-box" onSubmit={searchDeals}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search product (eg: laptop bag, serum, t-shirt)"
          aria-label="Search products"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {/* LOADER */}
      {loading && <p className="loading">Searching best deals…</p>}

      {/* ERROR */}
      {error && <div className="error-box">⚠️ {error}</div>}

      {/* FILTERS + SORT — only shown once results exist */}
      {results.length > 0 && (
        <div className="filter-bar">
          <div className="store-filters" role="group" aria-label="Filter by store">
            {STORES.map((store) => (
              <button
                key={store}
                type="button"
                className={`store-btn${activeStore === store ? " active" : ""}`}
                aria-pressed={activeStore === store}
                onClick={() => setActiveStore(store)}
              >
                {store}
              </button>
            ))}
          </div>

          <label className="sort-control">
            <span>Sort by</span>
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value)}
              aria-label="Sort products"
            >
              {SORT_MODES.map((mode) => (
                <option key={mode.value} value={mode.value}>
                  {mode.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {/* NO MATCHES FOR FILTER */}
      {results.length > 0 && visible.length === 0 && (
        <div className="error-box">No products match this store filter</div>
      )}

      {/* RESULTS */}
      {visible.length > 0 && (
        <div className="results">
          {visible.map((item, index) => {
            const offers = cardOffers(item, activeStore).map((offer, i) => ({
              ...offer,
              _index: i,
            }));
            const bestOffer = bestVisibleOffer(item, activeStore);
            const lowest = cheapestIndexes(offers);

            const headlinePrice =
              bestOffer?.price_display || item.best_price || "";
            const headlinePlatform =
              activeStore === "All Stores"
                ? item.best_platform || bestOffer?.platform || ""
                : bestOffer?.platform || item.best_platform || "";
            const headlineUrl =
              bestOffer?.url || item.best_url || "";

            return (
              <div className="card" key={index}>
                {/* CATEGORY BADGE */}
                <div className="category-badge">
                  {CATEGORY_ICONS[category]} {category}
                </div>

                {/* IMAGE */}
                {item.image ? (
                  <img
                    className="card-image"
                    src={item.image}
                    alt={item.title}
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                ) : (
                  <div className="card-image placeholder">
                    No image available
                  </div>
                )}

                <h3>{item.title}</h3>

                {/* BEST DEAL */}
                {headlinePrice && headlinePlatform && (
                  <div className="best-deal">
                    <p>
                      <b>Best price:</b> {headlinePrice} on {headlinePlatform}
                    </p>
                    <a
                      href={headlineUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Visit {headlinePlatform}
                    </a>
                  </div>
                )}

                {/* ALL OFFERS (filtered to the selected store) */}
                <div className="offers">
                  {offers.map((offer, i) => (
                    <div className="offer-row" key={offer._index}>
                      <span className="platform">{offer.platform}</span>

                      <span className="price">
                        {offer.price_display}
                        {lowest.has(i) && (
                          <span className="lowest-tag">Lowest</span>
                        )}
                      </span>

                      <a
                        className="btn"
                        href={offer.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Visit ${offer.platform}`}
                      >
                        Visit
                      </a>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}