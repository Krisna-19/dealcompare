import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

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

  const searchDeals = async (event) => {
    event.preventDefault();

    const trimmed = query.trim();
    if (!trimmed) return;

    setLoading(true);
    setError("");
    setResults([]);

    try {
      const res = await fetch(
        `${API_BASE}/search?query=${encodeURIComponent(trimmed)}`
      );

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

      {/* RESULTS */}
      {results.length > 0 && (
        <div className="results">
          {results.map((item, index) => {
            const lowest = cheapestIndexes(item.offers);

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
                {item.best_price && item.best_platform && (
                  <div className="best-deal">
                    <p>
                      <b>Best price:</b> {item.best_price} on{" "}
                      {item.best_platform}
                    </p>
                    <a
                      href={item.best_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Visit {item.best_platform}
                    </a>
                  </div>
                )}

                {/* ALL OFFERS */}
                <div className="offers">
                  {item.offers.map((offer, i) => (
                    <div className="offer-row" key={i}>
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