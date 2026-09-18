// Pure deal-ranking helper tests. Run with:  node dealcompare-ui/tests/deals.test.js
// (also picked up by `vitest run`). No network, no DOM.
import assert from "node:assert";

import {
  isValidOffer,
  validOffers,
  visibleOffers,
  bestOffer,
  priceDifference,
  sortOffers,
  offerPlatforms,
  mrpForOffer,
  savingsForOffer,
  availabilityForOffer,
  cardHasValidOffer,
  formatPrice,
  availableMarketplaces,
  marketplaceStatusSummary,
  marketplaceStatusLines,
} from "../src/lib/deals.js";

function offer(overrides = {}) {
  return {
    title: "Product",
    product_key: "product",
    platform: "Flipkart",
    price_value: 100,
    price_display: "\u20b9100",
    url: "https://www.flipkart.com/p?pid=X",
    image: "",
    ...overrides,
  };
}

// --- isValidOffer ---------------------------------------------------------
assert.strictEqual(isValidOffer(offer()), true, "real price + real url valid");
assert.strictEqual(isValidOffer(offer({ url: "" })), false, "empty url invalid");
assert.strictEqual(isValidOffer(offer({ url: null })), false, "null url invalid");
assert.strictEqual(isValidOffer(offer({ price_value: null })), false, "null price invalid");
assert.strictEqual(isValidOffer(offer({ price_value: 0 })), false, "zero price invalid");
assert.strictEqual(isValidOffer(offer({ price_value: -5 })), false, "negative price invalid");
assert.strictEqual(isValidOffer(offer({ price_value: "bad" })), false, "non-numeric price invalid");
assert.strictEqual(isValidOffer(null), false, "null offer invalid");

// --- validOffers ----------------------------------------------------------
const validSet = [offer({ platform: "Flipkart" }), offer({ platform: "Amazon", price_value: 0 }), offer({ platform: "Myntra", url: "" })];
assert.deepStrictEqual(
  validOffers(validSet).map((o) => o.platform),
  ["Flipkart"],
  "invalid offers are filtered out"
);

// --- visibleOffers (store filter + validity) ------------------------------
const multiCard = {
  title: "Watch",
  offers: [
    offer({ platform: "Flipkart", price_value: 999 }),
    offer({ platform: "Amazon", price_value: 1100 }),
  ],
};
assert.strictEqual(visibleOffers(multiCard, "All Stores").length, 2, "All Stores -> all offers");
assert.deepStrictEqual(visibleOffers(multiCard, "Amazon").map((o) => o.platform), ["Amazon"], "store filter narrows offers");
assert.strictEqual(visibleOffers(multiCard, "Myntra").length, 0, "store with no offer -> none");

// --- bestOffer ------------------------------------------------------------
const ranked = [
  offer({ platform: "Amazon", price_value: 1200 }),
  offer({ platform: "Flipkart", price_value: 899 }),
  offer({ platform: "Myntra", price_value: 950 }),
];
assert.strictEqual(bestOffer(ranked).platform, "Flipkart", "lowest valid price wins");
assert.strictEqual(bestOffer([]), null, "no offers -> no best");
assert.strictEqual(bestOffer([offer({ price_value: null })]), null, "no valid offers -> no best");

// --- mrpForOffer (backend-supplied only, never invented) ------------------
assert.strictEqual(mrpForOffer(offer({ price_value: 59900, mrp: 79900 })), 79900, "mrp supplied -> used");
assert.strictEqual(mrpForOffer(offer({ price_value: 59900, original_price: 79900 })), 79900, "original_price alias works");
assert.strictEqual(mrpForOffer(offer({ price_value: 59900, original_price_value: 79900 })), 79900, "original_price_value alias works");
assert.strictEqual(mrpForOffer(offer({ price_value: 59900, strike_price: 79900 })), 79900, "strike_price alias works");
assert.strictEqual(mrpForOffer(offer({ price_value: 59900 })), null, "no mrp supplied -> null");
assert.strictEqual(mrpForOffer(offer({ price_value: 79900, mrp: 59900 })), null, "mrp below price -> null (invalid)");
assert.strictEqual(mrpForOffer(offer({ price_value: 79900, mrp: 79900 })), null, "mrp equal to price -> null (no savings)");

// --- savingsForOffer ------------------------------------------------------
const savings = savingsForOffer(offer({ price_value: 59900, mrp: 79900 }));
assert.deepStrictEqual(savings, { mrp: 79900, current: 59900, saved: 20000, percent: 25 }, "savings math with rounded percent");
assert.strictEqual(savingsForOffer(offer({ price_value: 59900 })), null, "no mrp -> no savings");

// --- availabilityForOffer -------------------------------------------------
assert.deepStrictEqual(availabilityForOffer(offer({ in_stock: false })), { label: "Out of stock", tone: "out" }, "out of stock surfaced");
assert.deepStrictEqual(availabilityForOffer(offer({ availability: "Only 2 left" })), { label: "Only 2 left", tone: "text" }, "text availability surfaced");
assert.deepStrictEqual(availabilityForOffer(offer({ in_stock: true })), { label: "In stock", tone: "in" }, "in stock surfaced");
assert.strictEqual(availabilityForOffer(offer()), null, "no availability -> null");

// --- cardHasValidOffer ----------------------------------------------------
assert.strictEqual(cardHasValidOffer(multiCard), true, "card with valid offers ok");
assert.strictEqual(cardHasValidOffer({ offers: [offer({ price_value: null })] }), false, "card with invalid offers not ok");
assert.strictEqual(cardHasValidOffer({ offers: [] }), false, "card with no offers not ok");

// --- bestOffer (documented tie-break: first lowest in array order wins) ----
const tied = [
  offer({ platform: "Amazon", price_value: 100 }),
  offer({ platform: "Flipkart", price_value: 100 }),
  offer({ platform: "Myntra", price_value: 101 }),
];
assert.strictEqual(bestOffer(tied).platform, "Amazon", "tie -> first lowest in array order");
assert.strictEqual(bestOffer([offer({ price_value: null }), offer({ platform: "Ajio", price_value: 50 })]).platform, "Ajio", "invalid offers skipped before tie-break");
assert.strictEqual(bestOffer([offer({ price_value: null }), offer({ price_value: "" })]), null, "no valid -> null");

// --- priceDifference ------------------------------------------------------
const best = offer({ platform: "Flipkart", price_value: 55999 });
const dearer = offer({ platform: "Amazon", price_value: 57499 });
assert.strictEqual(priceDifference(best, dearer), 1500, "difference is offer - best");
assert.strictEqual(priceDifference(dearer, best), -1500, "symmetric difference");
assert.strictEqual(priceDifference(best, offer({ price_value: 55999 })), 0, "tie -> 0");
assert.strictEqual(priceDifference(best, offer({ price_value: null })), null, "invalid offer price -> null");
assert.strictEqual(priceDifference(offer({ price_value: null }), dearer), null, "invalid best price -> null");
assert.strictEqual(priceDifference(null, dearer), null, "no best -> null");

// --- sortOffers (deterministic; invalid excluded) --------------------------
const unsorted = [
  offer({ platform: "Myntra", price_value: 950 }),
  offer({ platform: "Amazon", price_value: 1200 }),
  offer({ platform: "Flipkart", price_value: 899 }),
  offer({ platform: "Ajio", price_value: 0 }),
  offer({ platform: "Croma", price_value: "" }),
];
assert.deepStrictEqual(sortOffers(unsorted, "best-first").map((o) => o.platform), ["Flipkart", "Myntra", "Amazon"], "best-first = ascending, invalid excluded");
assert.deepStrictEqual(sortOffers(unsorted, "price-asc").map((o) => o.platform), ["Flipkart", "Myntra", "Amazon"], "price-asc ascending");
assert.deepStrictEqual(sortOffers(unsorted, "price-desc").map((o) => o.platform), ["Amazon", "Myntra", "Flipkart"], "price-desc descending");

// Tie at equal price -> deterministic by platform name, then original order.
const tieSort = [
  offer({ platform: "Amazon", price_value: 500 }),
  offer({ platform: "Flipkart", price_value: 500 }),
  offer({ platform: "Ajio", price_value: 500 }),
];
assert.deepStrictEqual(
  sortOffers(tieSort, "price-asc").map((o) => o.platform),
  ["Ajio", "Amazon", "Flipkart"],
  "equal prices -> platform alphabetical (deterministic)"
);
assert.deepStrictEqual(
  sortOffers([offer({ platform: "Ajio", price_value: 1 }), offer({ platform: "Ajio", price_value: 1 })], "price-asc").map((o) => o.platform),
  ["Ajio", "Ajio"],
  "equal price+platform -> original order preserved (stable)"
);

// --- offerPlatforms (real marketplaces only) ------------------------------
const mixed = [
  offer({ platform: "Amazon", price_value: 0 }),
  offer({ platform: "Flipkart", price_value: 899 }),
  offer({ platform: "Flipkart", price_value: 900 }),
  offer({ platform: "Myntra", price_value: 950 }),
  offer({ platform: "Croma", price_value: "" }),
];
assert.deepStrictEqual(offerPlatforms(mixed), ["Flipkart", "Myntra"], "only marketplaces with valid offers, first-appearance order");
assert.deepStrictEqual(offerPlatforms([]), [], "no offers -> empty");

// --- availableMarketplaces (data-driven store filters) ---------------------
const groupedCards = [
  {
    title: "Wallet",
    offers: [
      offer({ platform: "Flipkart", price_value: 279 }),
      offer({ platform: "Amazon", price_value: 289 }),
      offer({ platform: "Myntra", price_value: 0 }), // invalid -> NOT a marketplace
    ],
  },
  {
    title: "Jacket",
    offers: [offer({ platform: "Amazon", price_value: 19999 })],
  },
];
assert.deepStrictEqual(
  availableMarketplaces(groupedCards),
  ["Flipkart", "Amazon"],
  "only marketplaces with at least one valid offer, first-appearance order"
);
assert.deepStrictEqual(availableMarketplaces([]), [], "no cards -> no marketplaces");
assert.deepStrictEqual(
  availableMarketplaces([{ title: "x", offers: [offer({ price_value: 0 })] }]),
  [],
  "marketplace whose offers are all invalid is never shown"
);

// --- marketplaceStatusSummary (backend summary, never invented) ------------
const rawSummary = [
  { key: "amazon", display_name: "Amazon", kind: "api", offer_count: 2, ok: true },
  { key: "flipkart", display_name: "Flipkart", kind: "api", offer_count: 0, ok: false },
  { key: "myntra", display_name: "Myntra", kind: "http", offer_count: 1, ok: true },
];
assert.deepStrictEqual(
  marketplaceStatusSummary(rawSummary),
  [
    { key: "amazon", display_name: "Amazon", ok: true, offer_count: 2 },
    { key: "flipkart", display_name: "Flipkart", ok: false, offer_count: 0 },
    { key: "myntra", display_name: "Myntra", ok: true, offer_count: 1 },
  ],
  "summary normalised to display-ready entries"
);
assert.deepStrictEqual(marketplaceStatusSummary(undefined), [], "no summary -> empty");
assert.deepStrictEqual(marketplaceStatusSummary([]), [], "empty summary -> empty");
assert.deepStrictEqual(
  marketplaceStatusLines(rawSummary),
  ["Amazon: 2 offers", "Flipkart: no offers right now", "Myntra: 1 offer"],
  "readable one-line statuses per source"
);

// --- formatPrice ----------------------------------------------------------
assert.strictEqual(formatPrice(59900), "\u20b959,900", "formats INR without decimals");
assert.strictEqual(formatPrice(0), "", "invalid price -> empty");
assert.strictEqual(formatPrice(null), "", "null price -> empty");

console.log("deals.test.js: all deal-ranking helper checks passed");