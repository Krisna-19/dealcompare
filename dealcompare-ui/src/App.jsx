import "./App.css";
import { Outlet } from "react-router-dom";

function App() {
  return (
    <div className="container">
      {/* HEADER */}
      <h1 className="title">DealCompare 🔥</h1>
      <p className="subtitle">Compare prices across multiple platforms</p>

      {/* 🔁 PAGE CONTENT CHANGES HERE */}
      <Outlet />

      {/* FOOTER */}
      <footer className="footer">
        <a href="/privacy">Privacy Policy</a> ·
        <a href="/terms">Terms & Conditions</a> ·
        <a href="/affiliate-disclosure">Affiliate Disclosure</a>

        <p style={{ fontSize: "12px", color: "#6b7280", marginTop: "12px" }}>
          As an Amazon Associate, we earn from qualifying purchases.
        </p>
      </footer>
    </div>
  );
}

export default App;
