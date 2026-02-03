import { useState, useEffect } from "react";

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sortOrder, setSortOrder] = useState("score");

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  // 🔍 SEARCH
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

  // 🔀 SORT RESULTS
  useEffect(() => {
    if (results.length === 0) return;

    const sorted = [...results];

    if (sortOrder === "low") {
      sorted.sort(
        (a, b) =>
          parseInt(a.best_deal.price.replace("₹", "").replace(",", "")) -
          parseInt(b.best_deal.price.replace("₹", "").replace(",", ""))
      );
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
    <>
      {/* 🔍 SEARCH BOX */}
      <div className="search-box">
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && searchDeals()}
          placeholder="Search product (eg: tshirt, iphone, shoes)"
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

      {/* ⏳ LOADING */}
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
            <div className="card-header">
              <h3>{item.product_name}</h3>
              <span className="badge best">BEST DEAL</span>
            </div>

            {/* BEST DEAL */}
            <div className="offer best">
              <p>
                <b>Price:</b> {item.best_deal.price}
                <br />
                <b>Platform:</b> {item.best_deal.platform}
                <br />
                <b>Rating:</b> ⭐ {item.best_deal.rating}
              </p>

              <a
                href={item.best_deal.product_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn"
              >
                View Best Deal →
              </a>
            </div>

            {/* OTHER OFFERS */}
            {item.other_offers?.length > 0 && (
              <details>
                <summary>Other offers</summary>

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
              </details>
            )}

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
    </>
  );
}
