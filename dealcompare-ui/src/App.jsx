import { Outlet } from "react-router-dom";
import "./App.css";

export default function App() {
  return (
    <div className="container">
      {/* HEADER */}
      <h1 className="title">
        DealCompare <span role="img">🔥</span>
      </h1>
      <p className="subtitle">
        Compare prices across multiple platforms
      </p>

      {/* PAGE CONTENT (HOME / PRIVACY / TERMS) */}
      <Outlet />

      {/* FOOTER */}
      <footer className="footer">
        <a href="/privacy">Privacy Policy</a> ·
        <a href="/terms">Terms & Conditions</a> ·
        <a href="/affiliate-disclosure">Affiliate Disclosure</a>

        <p className="disclaimer">
          As an Amazon Associate, we earn from qualifying purchases.
        </p>
      </footer>
    </div>
  );
}
