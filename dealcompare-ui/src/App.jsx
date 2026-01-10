import { useState, useEffect } from "react";
import "./App.css";

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sortOrder, setSortOrder] = useState("low");

  // ✅ FETCH ONLY
  const searchDeals = async () => {
    if (!query) return;

    setLoading(true);
    setError("");

    try {
      const res = await fetch(
        `https://dealcompare-api.onrender.com/search?query=${encodeURIComponent(query)}`
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

  // ✅ SORT WHEN sortOrder CHANGES
  useEffect(() => {
    if (results.length === 0) return;

    const sorted = [...results];

    if (sortOrder === "low") {
      sorted.sort((a, b) => {
        const priceA = parseInt(
          a.best_deal.price.replace("₹", "").replace(",", "")
        );
        const priceB = parseInt(
          b.best_deal.price.replace("₹", "").replace(",", "")
        );
        return priceA - priceB;
      });
    }

    if (sortOrder === "rating") {
      sorted.sort(
        (a, b) => b.best_deal.rating - a.best_deal.rating
      );
    }

    setResults(sorted);
  }, [sortOrder]);

  return (
    <div className="container">
      <h1 className="title">DealCompare 🔍</h1>
      <p className="subtitle">Compare prices across Amazon & Flipkart</p>

      <div className="search-box">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              searchDeals();
            }
          }}
          placeholder="Search product (eg: iphone)"
        />

        <button onClick={searchDeals} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>

      </div>

      <div className="sort-box">
        <label>Sort by:</label>
        <select
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value)}
        >
          <option value="low">💰 Price: Low → High</option>
          <option value="rating">⭐ Rating: High → Low</option>
        </select>
      </div>

      {loading && <p className="info">Loading deals...</p>}
      {error && <p className="error">{error}</p>}

      <div className="results">
        {results.map((item, i) => (
          <div className="card" key={i}>
            <div className="card-header">
              <h3>{item.product_name}</h3>
              <div className="badges">
                <span className="badge best">BEST DEAL</span>

                {item.other_offers.every(
                  o =>
                    parseInt(item.best_deal.price.replace("₹", "").replace(",", "")) <=
                    parseInt(o.price.replace("₹", "").replace(",", ""))
                ) && <span className="badge price">BEST PRICE</span>}

                {item.other_offers.every(
                  o => item.best_deal.rating >= o.rating
                ) && <span className="badge rating">BEST RATED</span>}
              </div>
            </div>

            <p><b>Brand:</b> {item.brand}</p>

            <div className="best-deal">
              <p>
                <b>Price:</b> {item.best_deal.price}<br />
                <b>Platform:</b> {item.best_deal.platform}<br />
                <b>Rating:</b> ⭐ {item.best_deal.rating}
              </p>

              <a
                href={item.best_deal.product_url}
                target="_blank"
                rel="noopener noreferrer"
                className="link"
              >
                View Product →
              </a>
            </div>

            {item.other_offers.length > 0 && (
              <div className="others">
                <h4>Other Offers</h4>
                {item.other_offers.map((o, j) => (
                  <p key={j} className="platform small">
                    {o.platform === "Amazon" ? "🟧 Amazon" : "🟦 Flipkart"} — {o.price}
                  </p>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
