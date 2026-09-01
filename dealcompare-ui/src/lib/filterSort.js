/* Pure store-filter + sort helpers shared by the React UI.

   These mirror the behaviour of the classic frontend (frontend/js/app.js)
   so the React rewrite behaves identically:

   - Store filtering acts on OFFERS of a canonical card. A card that has any
     offer from the selected store stays; the offers shown under a filter are
     restricted to that store. The headline price / platform / URL follow the
     BEST *visible* offer, so a card never advertises a hidden store's price.
   - Sorting uses the same effective (filtered) best price so the sort order
     and the Best Deal badge agree with the prices the user actually sees.

   Pure functions only (no DOM, no React) — unit-tested under Node.
 */

export const STORES = ["All Stores", "Amazon", "Flipkart", "Myntra", "Ajio"];

export const SORT_MODES = [
  { value: "best-deal", label: "Best Deal" },
  { value: "low-price", label: "Price: Low to High" },
  { value: "high-price", label: "Price: High to Low" },
];

function toNum(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/* Offers of a card visible under a store filter ("All Stores" => all). */
export function cardOffers(card, store) {
  if (!Array.isArray(card?.offers)) return [];
  let offers = card.offers;
  if (store && store !== "All Stores") {
    offers = offers.filter((o) => o && o.platform === store);
  }
  return offers;
}

/* Best (lowest-priced) offer of a card, respecting the store filter. */
export function bestVisibleOffer(card, store) {
  const offers = cardOffers(card, store);
  let best = null;
  for (const o of offers) {
    const val = toNum(o?.price_value);
    if (val != null && val > 0 && (!best || val < toNum(best.price_value))) {
      best = o;
    }
  }
  return best;
}

/* The price used for sorting and the Best Deal badge — the best *visible*
   offer's price so it matches what the card shows under the current filter. */
export function effectiveBestPrice(card, store) {
  const best = bestVisibleOffer(card, store);
  const val = best ? toNum(best.price_value) : null;
  return val != null ? val : null;
}

/* Keep cards that have at least one offer from the selected store. */
export function filterByStore(cards, store) {
  if (!Array.isArray(cards)) return [];
  if (!store || store === "All Stores") return cards.slice();
  return cards.filter((c) => cardOffers(c, store).length > 0);
}

/* Sort cards by their effective (filtered) best price. Sorting always uses
   the price the user actually sees, i.e. the best *visible* offer under the
   active store filter, so order and the Best Deal badge never contradict the
   displayed prices. */
export function sortProducts(cards, mode, store = "All Stores") {
  const arr = cards.slice();
  const priceOf = (c) => effectiveBestPrice(c, store);
  if (mode === "high-price") {
    arr.sort((a, b) => (priceOf(b) || 0) - (priceOf(a) || 0));
  } else {
    // best-deal and low-price are both ascending by price.
    arr.sort((a, b) => (priceOf(a) || Infinity) - (priceOf(b) || Infinity));
  }
  return arr;
}

/* The unique platforms present across every offer of every card. */
export function availableStores(cards) {
  const set = new Set();
  for (const c of cards || []) {
    for (const o of c?.offers || []) {
      if (o?.platform) set.add(o.platform);
    }
  }
  return Array.from(set);
}
