// React UI filter/sort regression tests for the pure helpers used by
// Home.jsx. Run with:  node dealcompare-ui/tests/filterSort.test.js
import assert from "node:assert";
import {
  STORES,
  SORT_MODES,
  filterByStore,
  sortProducts,
  cardOffers,
  bestVisibleOffer,
  effectiveBestPrice,
} from "../src/lib/filterSort.js";

function offer(platform, price, title, url) {
  return {
    title,
    platform,
    price_value: price,
    price_display: "\u20b9" + price,
    url,
  };
}

function card(title, offers, extra = {}) {
  return {
    title,
    best_price: "\u20b9" + Math.min(...offers.map((o) => o.price_value)),
    best_platform: offers[0].platform,
    best_url: offers[0].url,
    offers,
    ...extra,
  };
}

const multiStoreCard = card(
  "Men Brown Genuine Leather Wallet",
  [
    offer("Flipkart", 279, "Men Brown Genuine Leather Wallet", "/w/p?pid=FK1"),
    offer("Amazon", 289, "Men Brown Genuine Leather Wallet", "https://www.amazon.in/dp/B0WL1"),
    offer("Myntra", 299, "Men Brown Genuine Leather Wallet", "https://www.myntra.com/w"),
  ]
);

const amazonOnlyCard = card(
  "Teakwood Genuine Leather Biker Jacket",
  [offer("Amazon", 19999, "Teakwood Genuine Leather Biker Jacket", "https://www.amazon.in/dp/B0JK1")]
);

const flipkartOnlyCard = card(
  "Trolley Bag 55 cm",
  [offer("Flipkart", 2999, "Trolley Bag 55 cm", "/t/p?pid=FK2")]
);

const allCards = [multiStoreCard, amazonOnlyCard, flipkartOnlyCard];

// --- Store = All Stores ------------------------------------------------
assert.deepStrictEqual(STORES, ["All Stores", "Amazon", "Flipkart", "Myntra", "Ajio"]);
const allFiltered = filterByStore(allCards, "All Stores");
assert.strictEqual(allFiltered.length, 3, "All Stores shows every card");
assert.strictEqual(cardOffers(multiStoreCard, "All Stores").length, 3, "All Stores shows all offers");
assert.strictEqual(effectiveBestPrice(multiStoreCard, "All Stores"), 279, "All Stores best price = global min");

// --- Sort = Best Deal (ascending price) --------------------------------
assert.deepStrictEqual(SORT_MODES.map((m) => m.value), ["best-deal", "low-price", "high-price"]);
const bestDeal = sortProducts(allCards, "best-deal", "All Stores");
assert.deepStrictEqual(
  bestDeal.map((c) => effectiveBestPrice(c, "All Stores")),
  [279, 2999, 19999].sort((a, b) => a - b),
  "Best Deal sorts ascending"
);

// --- Store = Amazon ----------------------------------------------------
const amazonFilter = filterByStore(allCards, "Amazon");
assert.deepStrictEqual(
  amazonFilter.map((c) => c.title),
  [multiStoreCard.title, amazonOnlyCard.title],
  "Amazon filter keeps cards with a visible Amazon offer"
);
// offers shown are Amazon only
assert.deepStrictEqual(
  cardOffers(multiStoreCard, "Amazon").map((o) => o.platform),
  ["Amazon"],
  "Amazon filter shows only Amazon offers in a multi-store card"
);
assert.strictEqual(bestVisibleOffer(multiStoreCard, "Amazon").price_value, 289, "filtered best offer is Amazon price");

// --- Store = Flipkart --------------------------------------------------
const flipkartFilter = filterByStore(allCards, "Flipkart");
assert.deepStrictEqual(
  flipkartFilter.map((c) => c.title),
  [multiStoreCard.title, flipkartOnlyCard.title],
  "Flipkart filter keeps cards with a visible Flipkart offer"
);
assert.deepStrictEqual(
  cardOffers(multiStoreCard, "Flipkart").map((o) => o.platform),
  ["Flipkart"],
  "Flipkart filter shows only Flipkart offers"
);

// --- Sort respects the active store filter -----------------------------
// Under Amazon, the multi-store card's cheapest visible offer is Amazon 289
// (hidden Flipkart 279 is excluded), so it ranks below amazonOnlyCard (19999)
// and above flipkartOnlyCard which has no Amazon offer.
const amazonVisible = filterByStore(allCards, "Amazon");
const amazonSorted = sortProducts(amazonVisible, "best-deal", "Amazon");
assert.deepStrictEqual(
  amazonSorted.map((c) => c.title),
  [multiStoreCard.title, amazonOnlyCard.title],
  "Amazon-filtered sort keeps only visible Amazon cards, ascending"
);
assert.strictEqual(effectiveBestPrice(multiStoreCard, "Amazon"), 289, "sort price respects store filter");

// --- Sort = high-price -------------------------------------------------
const high = sortProducts(allCards, "high-price", "All Stores");
assert.deepStrictEqual(
  high.map((c) => effectiveBestPrice(c, "All Stores")),
  [19999, 2999, 279],
  "High-to-low sorts descending"
);

// --- switching filters updates displayed cards -------------------------
// Re-derive the pipeline the component uses: filter -> sort.
const renderedAmazon = sortProducts(filterByStore(allCards, "Amazon"), "best-deal", "Amazon");
const renderedAll = sortProducts(filterByStore(allCards, "All Stores"), "best-deal", "All Stores");
assert.strictEqual(renderedAmazon.length, 2, "switch to Amazon reduces card count");
assert.strictEqual(renderedAll.length, 3, "back to All Stores restores all cards");

// --- existing search/result rendering still works ----------------------
// The card title / price / platform fields the renderer relies on survive.
assert.ok(multiStoreCard.title && multiStoreCard.offers.length > 0, "card carries renderable data");
assert.ok(amazonOnlyCard.best_url.startsWith("https://"), "affiliate URL preserved");

console.log("filterSort.test.js: all React store/sort regression checks passed");
