import { useMemo, useState } from "react";
import {
  ALL_STORES,
  SORT_MODES,
  filterByStore,
  sortProducts,
} from "../lib/filterSort";
import {
  availableMarketplaces,
  marketplaceStatusSummary,
  visibleOffers,
} from "../lib/deals";
import SearchHeader from "../components/SearchHeader";
import ProductCard from "../components/ProductCard";
import { FeedbackState, LoadingCards } from "../components/FeedbackState";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

/* The free-tier backend can take a while (per-source timeouts under ~60s).
   Time out above that worst case so a slow-but-alive search is never aborted
   early, and add one retry to ride out a cold-start connection drop. */
const SEARCH_TIMEOUT_MS = 140000;

function fetchWithTimeout(url, timeoutMs = SEARCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { signal: controller.signal }).finally(() => clearTimeout(timer));
}

/* CATEGORY → ICON MAP (kept from the original Home; purely cosmetic) */
const CATEGORY_ICONS = {
  Fashion: "👕",
  Electronics: "💻",
  Beauty: "🧴",
  General: "🛒",
};

const EMPTY_COPY = {
  title: "No products found",
  hint: "Try a different product name or model. Some marketplaces may have no live offers for this search right now.",
};

const ERROR_COPY = {
  title: "Couldn’t compare prices",
  hint: "Our marketplace sources didn’t respond this time. Please try your search again in a moment.",
};

function categoryLabel(category) {
  return `${CATEGORY_ICONS[category] || ""} ${category}`.trim();
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | loading | done | empty | error
  const [results, setResults] = useState([]);
  const [marketplaces, setMarketplaces] = useState([]);
  const [category, setCategory] = useState("General");
  const [activeStore, setActiveStore] = useState(ALL_STORES);
  const [sortMode, setSortMode] = useState("best-deal");

  const searchDeals = async (rawQuery) => {
    const trimmed = (typeof rawQuery === "string" ? rawQuery : query).trim();
    if (!trimmed) return;

    // Search lifecycle resets. Derived/filtered lists never re-trigger fetches.
    setStatus("loading");
    setResults([]);
    setMarketplaces([]);
    setActiveStore(ALL_STORES);
    setSortMode("best-deal");
    setSearched(trimmed);

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
      const cards = Array.isArray(data.results) ? data.results : [];

      if (cards.length > 0) {
        setResults(cards);
        setMarketplaces(
          Array.isArray(data.marketplaces) ? data.marketplaces : []
        );
        setCategory(data.category || "General");
        setStatus("done");
      } else {
        setStatus("empty");
      }
    } catch {
      setStatus("error");
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (query.trim()) searchDeals(query);
  };

  const handleQuickSearch = (suggestion) => {
    setQuery(suggestion);
    searchDeals(suggestion);
  };

  /* Pure derived lists (memoized) — stable across the loading transition so
     nothing here can trigger an extra network request. */
  const cards = useMemo(
    () => sortProducts(filterByStore(results, activeStore), sortMode, activeStore),
    [results, activeStore, sortMode]
  );

  const offerCount = useMemo(
    () => results.reduce((total, card) => total + visibleOffers(card, ALL_STORES).length, 0),
    [results]
  );

  /* Per-source chips come ONLY from the data: the marketplaces that actually
     returned at least one valid offer.  A marketplace is never offered as a
     filter merely because it exists. */
  const availableMps = useMemo(() => availableMarketplaces(results), [results]);

  const availableLabel = useMemo(() => {
    const n = availableMps.length;
    if (n === 0) return "";
    return `Available on ${n} marketplace${n === 1 ? "" : "s"}`;
  }, [availableMps]);

  /* Honest per-source status (from the backend summary), shown only when the
     backend reports that a source that RAN produced no offers. */
  const statusLines = useMemo(
    () =>
      marketplaceStatusSummary(marketplaces)
        .filter((s) => !s.ok)
        .map((s) => `${s.display_name}: no offers right now`),
    [marketplaces]
  );

  return (
    <div className="container">
      <SearchHeader
        query={query}
        onQueryChange={setQuery}
        onSubmit={handleSubmit}
        onQuickSearch={handleQuickSearch}
        loading={status === "loading"}
        searched={searched}
        status={status}
        categoryLabel={status === "done" ? categoryLabel(category) : ""}
        resultCount={results.length}
        offerCount={offerCount}
      />

      {/* LOADING — polished skeleton */}
      {status === "loading" && <LoadingCards count={3} />}

      {/* ERROR — honest, actionable */}
      {status === "error" && (
        <FeedbackState
          variant="error"
          title={ERROR_COPY.title}
          hint={ERROR_COPY.hint}
        />
      )}

      {/* EMPTY — honest empty from the API */}
      {status === "empty" && (
        <FeedbackState
          variant="empty"
          title={EMPTY_COPY.title}
          hint={EMPTY_COPY.hint}
        />
      )}

      {/* RESULTS */}
      {status === "done" && (
        <>
          <div className="filter-bar" role="group" aria-label="Filter and sort results">
            <div className="store-filters">
              {[ALL_STORES, ...availableMps].map((store) => (
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
              <span className="sort-label">Sort by</span>
              <select
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value)}
                aria-label="Sort results"
              >
                {SORT_MODES.map((mode) => (
                  <option key={mode.value} value={mode.value}>
                    {mode.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {availableLabel && (
            <p className="results-meta" data-testid="available-marketplaces">
              {availableLabel}
            </p>
          )}
          {statusLines.length > 0 && (
            <p className="marketplace-status" data-testid="marketplace-status">
              {statusLines.join(" · ")}
            </p>
          )}

          {cards.length === 0 ? (
            <FeedbackState
              variant="filter"
              title="No matching results"
              hint="No marketplace offers match this store filter. Try a different store or clear the filter."
            />
          ) : (
            <div className="results">
              {cards.map((card, index) => (
                <ProductCard
                  key={`${card.title}-${index}`}
                  card={card}
                  offers={visibleOffers(card, activeStore)}
                  categoryLabel={categoryLabel(category)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* INITIAL STATE — guidance only, no fake data */}
      {status === "idle" && (
        <FeedbackState
          variant="search"
          title="Compare live prices across marketplaces"
          hint="Search for a product to see real offers and the best current price. If only one marketplace returns data, you’ll see only that marketplace."
        />
      )}
    </div>
  );
}