import { useState } from "react";
import "./App.css";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

/* CATEGORY → ICON MAP */
const CATEGORY_ICONS = {
  Fashion: "👕",
  Electronics: "💻",
  Beauty: "🧴",
  General: "🛒",
};

export default function App() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState([]);
  const [category, setCategory] = useState("General");

  const searchDeals = async () => {
    if (!query.trim()) return;

    setLoading(true);
    setError("");
    setResults([]);

    try {
      const res = await fetch(
        `${API_BASE_URL}/search?query=${encodeURIComponent(query)}`
      );

      if (!res.ok) throw new Error("API error");

      const data = await res.json();

      if (data.results && data.results.length > 0) {
        setResults(data.results);
        setCategory(data.category || "General");
      } else {
        setError("No products found");
      }
    } catch (err) {
      setError("Failed to fetch deals");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      {/* HEADER */}
      <h1 className="logo">DealCompare 🔥</h1>
      <p className="subtitle">Compare prices across multiple platforms</p>

      {/* SEARCH */}
      <div className="search-box">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && searchDeals()}
          placeholder="Search product (eg: laptop bag, serum, t-shirt)"
        />
        <button onClick={searchDeals} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {/* LOADER */}
      {loading && <p className="loading">Searching best deals…</p>}

      {/* ERROR */}
      {error && <div className="error">⚠️ {error}</div>}

      {/* RESULTS */}
      {results.map((item, idx) => (
        <div key={idx} className="product-card">
          {/* CATEGORY BADGE */}
          <div className="category-badge">
            {CATEGORY_ICONS[category]} {category}
          </div>

          <h2>{item.product_name}</h2>

          <div className="offers">
            {item.offers.map((offer, i) => (
              <div key={i} className="offer-row">
                <span className="platform">{offer.platform}</span>
                <span className="price">{offer.price}</span>

                <a
                  href={offer.product_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`btn ${offer.platform.toLowerCase()}`}
                  onClick={() =>
                    console.log(
                      "Clicked:",
                      offer.platform,
                      item.product_name
                    )
                  }
                >
                  Visit {offer.platform}
                </a>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* FOOTER */}
      <footer>
        <p className="disclaimer">
          As an Amazon Associate, we earn from qualifying purchases.
        </p>

        <div className="links">
          <a href="/privacy">Privacy Policy</a>
          <a href="/terms">Terms & Conditions</a>
          <a href="/affiliate">Affiliate Disclosure</a>
        </div>
      </footer>
    </div>
  );
}
