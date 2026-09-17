/* Price-history helpers + the read-only history fetch.

   History data comes ONLY from the backend's read-only catalog endpoint
   (GET /products/{product_key}/price-history), which serves the real
   PriceSnapshot rows the catalog accumulated over time.  Nothing in this
   module invents prices, dates, observations or trends: every value the UI
   shows is derived strictly from the observations the API actually returned
   (or an honest "not available" state when there are none).
*/

import { toPrice } from "./deals.js";

/* Vite injects import.meta.env; plain-node tests fall back to the default. */
const API_BASE =
  import.meta.env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchPriceHistory(productKey, options = {}) {
  const url = `${API_BASE}/products/${encodeURIComponent(productKey)}/price-history`;
  const res = await fetch(url, { signal: options.signal });
  if (!res.ok) throw new Error("Price history unavailable");
  return res.json();
}

/* Fetch history for several listings in parallel and merge the per-key offers.
   Each key keeps its own offer series; nothing is cross-correlated here. */
export async function fetchPriceHistories(keys, options = {}) {
  const uniqueKeys = (Array.isArray(keys) ? keys : []).filter(
    (key, index, all) =>
      typeof key === "string" && key.trim() && all.indexOf(key) === index
  );
  const responses = await Promise.all(
    uniqueKeys.map((key) => fetchPriceHistory(key, options))
  );
  const merged = [];
  for (const response of responses) {
    if (Array.isArray(response?.offers)) merged.push(...response.offers);
  }
  return merged;
}

/* Distinct, non-empty product_key values (only real listing identities). */
export function uniqProductKeys(offers) {
  const seen = new Set();
  const keys = [];
  for (const offer of Array.isArray(offers) ? offers : []) {
    const key = typeof offer?.product_key === "string" ? offer.product_key.trim() : "";
    if (key && !seen.has(key)) {
      seen.add(key);
      keys.push(key);
    }
  }
  return keys;
}

/* Aggregate stats of a real observation list.  Returns null when the list has
   no usable (finite, positive-price, dated) observation — the UI never gets a
   fabricated value from junk or empty input. */
export function observationStats(observations) {
  const obs = (Array.isArray(observations) ? observations : []).filter(
    (o) =>
      o &&
      typeof o === "object" &&
      toPrice(o.price_value) != null &&
      Number.isFinite(Number(o.observed_at))
  );
  if (obs.length === 0) return null;
  const prices = obs.map((o) => toPrice(o.price_value));
  const times = obs.map((o) => Number(o.observed_at));
  return {
    count: obs.length,
    low: Math.min(...prices),
    high: Math.max(...prices),
    firstAt: Math.min(...times),
    lastAt: Math.max(...times),
  };
}

/* Normalize backend history offers into chart/summary series.  Series with no
   usable observations are dropped: they contribute nothing (never a fake
   point).  Each series remains one marketplace listing. */
export function historySummaries(responseOffers) {
  return (Array.isArray(responseOffers) ? responseOffers : [])
    .map((s) => {
      if (!s || typeof s !== "object") return null;
      const stats = observationStats(s.observations);
      if (!stats) return null;
      return {
        productKey: typeof s.product_key === "string" ? s.product_key : "",
        platform: typeof s.platform === "string" ? s.platform : "",
        title: typeof s.title === "string" ? s.title : "",
        url: typeof s.url === "string" ? s.url : "",
        currentPrice: toPrice(s.current_price),
        observations: (Array.isArray(s.observations) ? s.observations : [])
          .filter(
            (o) =>
              o &&
              toPrice(o.price_value) != null &&
              Number.isFinite(Number(o.observed_at))
          )
          .map((o) => ({
            price_value: toPrice(o.price_value),
            observed_at: Number(o.observed_at),
          }))
          .sort((a, b) => a.observed_at - b.observed_at),
        stats,
      };
    })
    .filter(Boolean);
}

/* Whole-modal summary derived ONLY from the supplied series.  Returns null
   when there is nothing real to summarize. */
export function historySummary(series) {
  if (!Array.isArray(series) || series.length === 0) return null;
  return series.reduce(
    (acc, s) => {
      const st = s.stats;
      acc.count += st.count;
      acc.low = acc.low == null ? st.low : Math.min(acc.low, st.low);
      acc.high = acc.high == null ? st.high : Math.max(acc.high, st.high);
      acc.firstAt =
        acc.firstAt == null ? st.firstAt : Math.min(acc.firstAt, st.firstAt);
      acc.lastAt =
        acc.lastAt == null ? st.lastAt : Math.max(acc.lastAt, st.lastAt);
      return acc;
    },
    { count: 0, low: null, high: null, firstAt: null, lastAt: null }
  );
}

/* Format an epoch-seconds timestamp as "dd Mmm yyyy" (en-IN). */
export function formatHistoryDate(epochSeconds) {
  if (
    epochSeconds === null ||
    epochSeconds === undefined ||
    epochSeconds === "" ||
    (typeof epochSeconds !== "number" && typeof epochSeconds !== "string")
  ) {
    return "";
  }
  const ms = Number(epochSeconds);
  if (!Number.isFinite(ms)) return "";
  return new Date(ms * 1000).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}