import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import App from "./App";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import Affiliate from "./pages/Affiliate";

ReactDOM.createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <Route path="/" element={<App />}>
      <Route index element={<Home />} />
      <Route path="privacy" element={<Privacy />} />
      <Route path="terms" element={<Terms />} />
      <Route path="affiliate-disclosure" element={<Affiliate />} />
    </Route>
  </BrowserRouter>
);
