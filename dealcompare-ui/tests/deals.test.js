// Pure deal-ranking helper tests. Run with:  node dealcompare-ui/tests/deals.test.js
// (also picked up by `vitest run`). No network, no DOM.
import assert from "node:assert";

import {
  isValidOffer,
  validOffers,
  visibleOffers,
  bestOffer,
  mrpForOffer,
  savingsForOffer,
  availabilityForOffer,
  cardHasValidOffer,
  formatPrice,
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

// --- formatPrice ----------------------------------------------------------
assert.strictEqual(formatPrice(59900), "\u20b959,900", "formats INR without decimals");
assert.strictEqual(formatPrice(0), "", "invalid price -> empty");
assert.strictEqual(formatPrice(null), "", "null price -> empty");

console.log("deals.test.js: all deal-ranking helper checks passed");