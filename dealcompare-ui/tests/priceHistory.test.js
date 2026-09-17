// Pure price-history helper tests.  Run with:  node dealcompare-ui/tests/priceHistory.test.js
// (also picked up by `vitest run`).  No network, no DOM.  These helpers only
// SELECT and AGGREGATE real observations — they never fabricate a price, date
// or trend point.
import assert from "node:assert";

import {
  uniqProductKeys,
  observationStats,
  historySummaries,
  historySummary,
  formatHistoryDate,
} from "../src/lib/priceHistory.js";

// --- uniqProductKeys --------------------------------------------------------
assert.deepStrictEqual(
  uniqProductKeys([
    { product_key: "fk-iphone-15-128" },
    { product_key: "fk-iphone-15-128" },
    { product_key: "am-iphone-15-128" },
  ]),
  ["fk-iphone-15-128", "am-iphone-15-128"],
  "dedupes keys, keeps first-appearance order"
);
assert.deepStrictEqual(uniqProductKeys([{ product_key: " " }, { product_key: "" }, {}]), [], "blank/missing keys ignored");
assert.deepStrictEqual(uniqProductKeys(null), [], "non-array input -> empty");
assert.deepStrictEqual(uniqProductKeys([]), [], "empty list -> empty");

// --- observationStats -------------------------------------------------------
assert.strictEqual(observationStats([]), null, "no observations -> null");
assert.strictEqual(observationStats(null), null, "null observations -> null");
assert.strictEqual(observationStats([{}]), null, "junk observation -> null");
assert.strictEqual(
  observationStats([{ price_value: 0, observed_at: 100 }, { price_value: "bad", observed_at: 200 }]),
  null,
  "no usable observation -> null"
);

const stats = observationStats([
  { price_value: 59900, observed_at: 1600000000 },
  { price_value: "58400", observed_at: 1590000000 },
  { price_value: 61000, observed_at: 1610000000 },
]);
assert.deepStrictEqual(
  stats,
  { count: 3, low: 58400, high: 61000, firstAt: 1590000000, lastAt: 1610000000 },
  "aggregates only real observations"
);
assert.strictEqual(stats.count, 3, "all three observations kept");

// --- historySummaries -------------------------------------------------------
const series = historySummaries([
  {
    product_key: "fk-iphone-15-128",
    platform: "Flipkart",
    title: "Apple iPhone 15 (128 GB)",
    url: "https://flipkart/x",
    current_price: 59900,
    observations: [
      { price_value: 64000, observed_at: 200 },
      { price_value: 59900, observed_at: 100 },
    ],
  },
  {
    product_key: "am-iphone-15-128",
    platform: "Amazon",
    title: "Apple iPhone 15 (128 GB)",
    url: "https://amazon/x",
    current_price: null,
    observations: [{ price_value: 0, observed_at: 50 }],
  },
  null,
]);
assert.strictEqual(series.length, 1, "only real (usable) series survive");
assert.strictEqual(series[0].platform, "Flipkart", "usable series kept");
assert.deepStrictEqual(
  series[0].observations.map((o) => o.observed_at),
  [100, 200],
  "series observations sorted chronologically"
);
assert.strictEqual(series[0].stats.low, 59900, "series low computed");
assert.strictEqual(series[0].stats.high, 64000, "series high computed");
assert.strictEqual(series[0].currentPrice, 59900, "current price carried as a number");

assert.deepStrictEqual(
  historySummaries([{ product_key: "x", platform: "Flipkart", observations: [] }]),
  [],
  "empty observations drop the series"
);

// --- historySummary (overall, built only from supplied real series) ----------
assert.strictEqual(historySummary([]), null, "no series -> null");
assert.strictEqual(historySummary(null), null, "null -> null");
const overall = historySummary(
  historySummaries([
    {
      product_key: "fk",
      platform: "Flipkart",
      observations: [
        { price_value: 59000, observed_at: 100 },
        { price_value: 62000, observed_at: 200 },
      ],
    },
    {
      product_key: "am",
      platform: "Amazon",
      observations: [
        { price_value: 59500, observed_at: 120 },
        { price_value: 61500, observed_at: 180 },
      ],
    },
  ])
);
assert.deepStrictEqual(
  overall,
  { count: 4, low: 59000, high: 62000, firstAt: 100, lastAt: 200 },
  "aggregates across series without merging identities"
);

// --- formatHistoryDate ------------------------------------------------------
assert.strictEqual(formatHistoryDate(0), "01 Jan 1970", "epoch -> 01 Jan 1970 (en-IN)");
assert.strictEqual(formatHistoryDate(null), "", "invalid timestamp -> empty");

console.log("priceHistory.test.js: all price-history helper checks passed");