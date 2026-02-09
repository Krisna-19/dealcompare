import { useState } from "react";

export default function Home() {
  const [query, setQuery] = useState("");

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
        />
        <button>Search</button>
      </div>

      {/* FOOTER / AMAZON DISCLOSURE */}
      <div className="footer">
        <p>
          As an Amazon Associate, we earn from qualifying purchases.
        </p>

        <div>
          <a href="/privacy">Privacy Policy</a>
          <a href="/terms">Terms & Conditions</a>
          <a href="/affiliate">Affiliate Disclosure</a>
        </div>
      </div>
    </div>
  );
}
