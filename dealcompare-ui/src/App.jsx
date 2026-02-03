import { Outlet } from "react-router-dom";

function App() {
  return (
    <div className="container">
      <h1>DealCompare 🔥</h1>
      <p>Compare prices across multiple platforms</p>

      {/* THIS IS REQUIRED */}
      <Outlet />

      <footer className="footer">
        <a href="/privacy">Privacy Policy</a> ·
        <a href="/terms">Terms & Conditions</a> ·
        <a href="/affiliate-disclosure">Affiliate Disclosure</a>

        <p style={{ fontSize: "12px", marginTop: "10px" }}>
          As an Amazon Associate, we earn from qualifying purchases.
        </p>
      </footer>
    </div>
  );
}

export default App;
