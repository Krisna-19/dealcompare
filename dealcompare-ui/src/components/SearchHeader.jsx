import { SUGGESTIONS } from "./suggestions.js";

function MagnifierIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <circle
        cx="9"
        cy="9"
        r="6.25"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <line x1="14" y1="14" x2="17" y2="17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/* Top hero: brand, responsive search bar, quick-search suggestions and the
   "results for <query>" summary.  All interaction routes through Home. */
export default function SearchHeader({
  query,
  onQueryChange,
  onSubmit,
  onQuickSearch,
  loading,
  searched,
  status,
  categoryLabel,
  resultCount,
  offerCount,
}) {
  const showSummary = searched != null && status !== "idle" && status !== "loading";

  return (
    <header className="hero">
      <h1 className="title">
        DealCompare <span className="title-mark" aria-hidden="true">🔥</span>
      </h1>
      <p className="subtitle">Compare live prices across marketplaces and land the best deal.</p>

      <form className="search-box" role="search" onSubmit={onSubmit}>
        <div className="search-field">
          <span className="search-icon" aria-hidden="true">
            <MagnifierIcon />
          </span>
          <input
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="e.g. iPhone 15, Samsung Galaxy S24, laptop"
            aria-label="Search products"
            autoComplete="off"
            inputMode="search"
          />
          {loading && <span className="search-spinner" role="status" aria-label="Searching">…</span>}
        </div>
        <button type="submit" className="btn btn-primary btn-search" disabled={loading}>
          {loading ? "Searching…" : "Compare"}
        </button>
      </form>

      {status === "idle" && (
        <div className="quick-chips" aria-label="Popular searches">
          <span className="quick-chips-label">Try:</span>
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              className="chip"
              aria-label={`Search for ${s}`}
              onClick={() => onQuickSearch(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {showSummary && (
        <div className="results-summary" aria-live="polite">
          {status === "done" && (
            <>
              {categoryLabel && <span className="summary-category">{categoryLabel}</span>}
              <span className="summary-text">
                Showing <strong>{resultCount} {resultCount === 1 ? "product" : "products"}</strong>
                {" · "}
                <strong>{offerCount} {offerCount === 1 ? "offer" : "offers"}</strong>
                {" for "}
                <span className="summary-query">“{searched}”</span>
              </span>
            </>
          )}
          {status === "empty" && (
            <span className="summary-text">
              No products found for <span className="summary-query">“{searched}”</span>
            </span>
          )}
          {status === "error" && (
            <span className="summary-text">
              Search for <span className="summary-query">“{searched}”</span> could not be completed
            </span>
          )}
        </div>
      )}
    </header>
  );
}