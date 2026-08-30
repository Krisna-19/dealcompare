import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const searchDeals = async () => {
    if (!query.trim()) return;

    setLoading(true);
    setError("");
    setResults([]);

    try {
      const res = await fetch(
        `${API_BASE}/search?query=${encodeURIComponent(query)}`
      );

      const data = await res.json();

      if (data.results && data.results.length > 0) {
        setResults(data.results.slice(0, 3)); // TOP 3 PRODUCTS
      } else {
        setError("No deals found");
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
      <h1 className="title">
        DealCompare <span role="img">🔥</span>
      </h1>
      <p className="subtitle">
        Compare prices across multiple platforms
      </p>

      {/* SEARCH */}
      <div className="search-box">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search product (eg: laptop bag, serum, t-shirt)"
          onKeyDown={(e) => e.key === "Enter" && searchDeals()}
        />
        <button onClick={searchDeals} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {/* ERROR */}
      {error && <div className="error-box">⚠️ {error}</div>}

      {/* RESULTS */}
      {results.length > 0 && (
        <div className="results">
          {results.map((item, index) => (
            <div className="card" key={index}>
              <h3>{item.product_name}</h3>

              {/* BEST DEAL */}
              {item.best_deal && (
                <div className="best-deal">
                  <p>
                    <b>{item.best_deal.platform}</b> – ₹{item.best_deal.price}
                  </p>
                  <a
                    href={item.best_deal.product_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Visit {item.best_deal.platform}
                  </a>
                </div>
              )}

              {/* OTHER OFFERS */}
              {item.other_offers?.length > 0 && (
                <div className="other-offers">
                  <p><b>Other offers:</b></p>
                  {item.other_offers.map((offer, i) => (
                    <div key={i}>
                      {offer.platform} – ₹{offer.price}{" "}
                      <a
                        href={offer.product_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Visit
                      </a>
                    </div>
                  ))}
                </div>
              )}

              {/* AMAZON FALLBACK */}
              {item.amazon_affiliate_url && (
                <div className="amazon">
                  <a
                    href={item.amazon_affiliate_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    View on Amazon
                  </a>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* FOOTER / AMAZON DISCLOSURE */}
      <div className="footer">
        <p>
          As an Amazon Associate, we earn from qualifying purchases.
        </p>

        <div className="footer-links">
          <a href="/privacy">Privacy Policy</a>
          <a href="/terms">Terms & Conditions</a>
          <a href="/affiliate">Affiliate Disclosure</a>
        </div>
      </div>
    </div>
  );
}
