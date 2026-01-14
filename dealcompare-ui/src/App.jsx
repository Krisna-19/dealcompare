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
  const [sortOrder, setSortOrder] = useState("low");

  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // 🔍 SEARCH API
  const searchDeals = async () => {
    if (!query) return;

    setLoading(true);
    setError("");
    setShowSuggestions(false);

    try {
      const res = await fetch(
        `http://127.0.0.1:8000/search?query=${encodeURIComponent(query)}`
    );


      if (!res.ok) throw new Error("API error");

      const data = await res.json();
      setResults(data.results || []);
    } catch (err) {
      setError("Failed to fetch deals");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // 💡 AUTOSUGGEST INPUT HANDLER
  const handleInput = async (value) => {
  setQuery(value);

  if (value.length < 2) {
    setSuggestions([]);
    setShowSuggestions(false);
    return;
  }

  try {
    const res = await fetch(
      `http://127.0.0.1:8000/suggest?query=${encodeURIComponent(value)}`
    );
    const data = await res.json();

    setSuggestions(data);
    setShowSuggestions(true);
  } catch (err) {
    console.error("Suggestion fetch failed", err);
  }
};


  // 🔃 SORT WHEN sortOrder CHANGES
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
      <h1 className="title">DealCompare 🔍</h1>
      <p className="subtitle">Compare prices across Amazon & Flipkart</p>

      {/* 🔎 SEARCH BOX */}
      <div className="search-box">
  <input
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

  <button onClick={searchDeals} disabled={loading}>
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


      {/* 🔃 SORT */}
      <div className="sort-box">
        <label>Sort by:</label>
        <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
          <option value="low">💰 Price: Low → High</option>
          <option value="rating">⭐ Rating: High → Low</option>
          <option value="score">🧠 Smart Score</option> 
        </select>
      </div>

      {loading && <p className="info">Loading deals...</p>}
      {error && <p className="error">{error}</p>}

      {/* 🧾 RESULTS */}
      <div className="results">
        {results.map((item, i) => (
          <div className="card" key={i}>
            <div className="card-header">
              <h3>{item.product_name}</h3>
              <span className="badge best">BEST DEAL</span>
            </div>

            <p><b>Brand:</b> {item.brand}</p>

            <div className="best-deal">
          <p>
                <b>Price:</b> {item.best_deal.price}<br />
                <b>Platform:</b> {item.best_deal.platform}<br />
                <b>Rating:</b> ⭐ {item.best_deal.rating}
                <span
                  className={`score-badge tooltip ${getScoreClass(item.best_deal.score)}`}
                >
                  🧠 Score: {item.best_deal.score.toFixed(2)}

                  <span className="tooltip-text">
                    Smart Score combines<br />
                    💰 Price (40%)<br />
                    ⭐ Rating (40%)<br />
                    🚚 Delivery speed (20%)<br />
                    Higher score = better deal
                  </span>
                </span>
              </p>
          {/* ✅ SMART SCORE BADGE */}
          {item.best_deal.score !== undefined && (
            <div className={`score-badge ${getScoreClass(item.best_deal.score)}`}>
              🏆 Smart Score: {item.best_deal.score.toFixed(2)}
            </div>
  )}

        <a
          href={item.best_deal.product_url}
          target="_blank"
          rel="noopener noreferrer"
          className="link"
        >
          View Product →
        </a>
      </div>

          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
