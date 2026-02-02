import { useState, useEffect } from "react";
import "./App.css";

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sortOrder, setSortOrder] = useState("score");

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  /* 🔍 SEARCH */
  const searchDeals = async () => {
    if (!query.trim()) return;

    try {
      setLoading(true);
      setError("");
      setResults([]);

      const res = await fetch(
        `${API_BASE_URL}/search?query=${encodeURIComponent(query)}`
      );

      if (!res.ok) throw new Error("API error");

      const data = await res.json();

      if (data.results && data.results.length > 0) {
        setResults(data.results);
      } else {
        setError("No deals found");
      }
    } catch (err) {
      console.error(err);
      setError("Failed to fetch deals");
    } finally {
      setLoading(false);
    }
  };

  /* 🔀 SORT */
  useEffect(() => {
    if (results.length === 0) return;

    const sorted = [...results];

    if (sortOrder === "low") {
      sorted.sort((a, b) => {
        const pA = parseInt(a.best_deal.price.replace("₹", "").replace(",", ""));
        const pB = parseInt(b.best_deal.price.replace("₹", "").replace(",", ""));
        return pA - pB;
      });
    }

    if (sortOrder === "rating") {
      sorted.sort(
        (a, b) => (b.best_deal.rating || 0) - (a.best_deal.rating || 0)
      );
    }

    if (sortOrder === "score") {
      sorted.sort(
        (a, b) => (b.best_deal.score || 0) - (a.best_deal.score || 0)
      );
    }

    setResults(sorted);
  }, [sortOrder]);

  return (
    <div className="container">
      <h1 className="title">DealCompare 🔥</h1>
      <p className="subtitle">Compare prices across multiple platforms</p>

      {/* 🔍 SEARCH BOX */}
      <div className="search-box">
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && searchDeals()}
          placeholder="Search product (eg: tshirt)"
        />
        <button onClick={searchDeals} disabled={loading || !query.trim()}>
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {/* 🔀 SORT */}
      {results.length > 0 && (
        <div className="sort-box">
          <label>Sort by:</label>
          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
          >
            <option value="score">Smart Score</option>
            <option value="low">Price: Low → High</option>
            <option value="rating">Rating: High → Low</option>
          </select>
        </div>
      )}

      {/* 🔄 LOADER */}
      {loading && (
        <div className="loader">
          <div className="spinner"></div>
          <p>Searching best deals...</p>
        </div>
      )}

      {/* ❌ ERROR */}
      {error && <div className="error-box">⚠️ {error}</div>}

      {/* 🟢 RESULTS */}
      <div className="results">
        {results.map((item, i) => (
          <div className="card" key={i}>
            <h3>{item.product_name}</h3>

            {/* BEST DEAL */}
            <div className="offer best">
              <span>{item.best_deal.platform}</span>
              <span>{item.best_deal.price}</span>
              <a
                href={item.best_deal.product_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn"
              >
                Visit {item.best_deal.platform}
              </a>
            </div>

            {/* OTHER OFFERS */}
            {item.other_offers.map((o, idx) => (
              <div className="offer" key={idx}>
                <span>{o.platform}</span>
                <span>{o.price}</span>
                <a
                  href={o.product_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn secondary"
                >
                  Visit {o.platform}
                </a>
              </div>
            ))}

            {/* AMAZON */}
            {item.amazon_affiliate_url && (
              <div className="offer">
                <span>Amazon</span>
                <span>Check price</span>
                <a
                  href={item.amazon_affiliate_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn secondary"
                >
                  Visit Amazon
                </a>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ✅ AMAZON COMPLIANCE */}
      <p style={{ fontSize: "12px", color: "#6b7280", marginTop: "40px" }}>
        As an Amazon Associate, we earn from qualifying purchases.
      </p>
      <footer className="footer">
        <a href="/privacy">Privacy Policy</a> ·
        <a href="/terms">Terms & Conditions</a> ·
        <a href="/affiliate-disclosure">Affiliate Disclosure</a>
      </footer>

    </div>
  );
}

export default App;
