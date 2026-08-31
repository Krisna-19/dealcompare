import { Outlet } from "react-router-dom";
import "./App.css";

export default function App() {
  return (
    <>
      <main>
        <Outlet />
      </main>

      {/* FOOTER / AMAZON DISCLOSURE */}
      <footer className="footer">
        <p>As an Amazon Associate, we earn from qualifying purchases.</p>

        <div className="footer-links">
          <a href="/privacy">Privacy Policy</a>
          <a href="/terms">Terms & Conditions</a>
          <a href="/affiliate">Affiliate Disclosure</a>
        </div>
      </footer>
    </>
  );
}