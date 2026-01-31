import { useState, useEffect } from "react";
import "./App.css";

const getScoreClass = (score) => {
  if (score >= 0.8) return "score-green";
  if (score >= 0.6) return "score-yellow";
  return "score-red";
};

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sortOrder, setSortOrder] = useState("score");

  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  /* 🔍 SEARCH */
  const searchDeals = async () => {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(
        `${API_BASE_URL}/search?query=${encodeURIComponent(query)}`    
      );
      console.log("API URL:", API_BASE_URL);

      if (!res.ok) {
        throw new Error("API error");
      }

      const data = await res.json();

      if (data.results && data.results.length > 0) {
        setResults(data.results);
        setError("");
      } else {
        setResults([]);
        setError("No deals found");
      }
    } catch (err) {
      console.error(err);
      setError("Failed to fetch deals");
    } finally {
      setLoading(false);
    }
  };

  /* 🔍 AUTOSUGGEST */
  const handleInput = async (value) => {
    setQuery(value);

    if (value.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE_URL}/suggest?query=${encodeURIComponent(value)}`
      );
      const data = await res.json();
      setSuggestions(data);
      setShowSuggestions(true);
    } catch (err) {
      console.error("Suggestion fetch failed", err);
    }
  };

  /* 🔀 SORT */
  useEffect(() => {
    if (results.length === 0) return;

    const sorted = [...results];

    if (sortOrder === "low") {
      sorted.sort((a, b) => {
        const priceA = parseInt(a.best_deal.price.replace("₹", "").replace(",", ""));
        const priceB = parseInt(b.best_deal.price.replace("₹", "").replace(",", ""));
        return priceA - priceB;
      });
    }

    if (sortOrder === "rating") {
      sorted.sort((a, b) => b.best_deal.rating - a.best_deal.rating);
    }

    if (sortOrder === "score") {
      sorted.sort((a, b) => b.best_deal.score - a.best_deal.score);
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
          onChange={(e) => handleInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setShowSuggestions(false);
              searchDeals();
            }
          }}
          placeholder="Search product (eg: tshirt)"
        />

        <button onClick={searchDeals} disabled={loading || !query.trim()}>
          {loading ? "Searching..." : "Search"}
        </button>

        {showSuggestions && suggestions.length > 0 && (
          <ul className="suggestions">
            {suggestions.map((s, i) => (
              <li
                key={i}
                onClick={() => {
                  setQuery(s);
                  setShowSuggestions(false);
                  searchDeals();
                }}
              >
                {s}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 🔀 SORT */}
      <div className="sort-box">
        <label>Sort by:</label>
        <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
          <option value="score">Smart Score</option>
          <option value="low">Price: Low → High</option>
          <option value="rating">Rating: High → Low</option>
        </select>
      </div>

      {/* 🔄 LOADER */}
      {loading && (
        <div className="loader">
          <div className="spinner"></div>
          <p>Searching best deals...</p>
        </div>
      )}

      {/* ❌ ERROR */}
      {error && <div className="error-box">⚠️ {error}</div>}

      {/* 📭 NO RESULTS */}
      {!loading && results.length === 0 && query && !error && (
        <div className="no-results">
          No deals found for <b>{query}</b>
        </div>
      )}

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
      {item.other_offers.map((offer, idx) => (
        <div className="offer" key={idx}>
          <span>{offer.platform}</span>
          <span>{offer.price}</span>

          <a
            href={offer.product_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn secondary"
          >
            Visit {offer.platform}
          </a>
        </div>
      ))}

      {/* AMAZON (OPTIONAL) */}
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
    </div>
  );
}

export default App;
