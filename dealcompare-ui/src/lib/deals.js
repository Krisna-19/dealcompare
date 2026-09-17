/* Pure deal-ranking helpers for the results UI.

   The API (GET /search) is the single source of truth.  Offers carry at
   minimum: { platform, price_value, price_display, url }.  These helpers
   only SELECT and DISPLAY data the API actually returned — they never
   fabricate prices, prices, marketplaces, savings or availability.

   Optional fields an offer MAY carry (if the backend supplies them):
   mrp / original_price / original_price_value / strike_price,
   availability, in_stock, is_available.
*/

import { cardOffers } from "./filterSort.js";

export function toPrice(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/* An offer is "valid" only when it has a real price and a real URL. */
export function isValidOffer(offer) {
  return (
    offer != null &&
    typeof offer === "object" &&
    typeof offer.url === "string" &&
    offer.url.length > 0 &&
    toPrice(offer.price_value) != null
  );
}

/* Offers of a card that are actually usable (real price + URL). */
export function validOffers(offers) {
  if (!Array.isArray(offers)) return [];
  return offers.filter(isValidOffer);
}

/* Offers of a card under a store filter, restricted to valid ones. */
export function visibleOffers(card, store) {
  return validOffers(cardOffers(card, store));
}

/* The lowest-priced valid offer of a list (null when none are valid).

   Tie-break rule (documented + tested): when two or more offers share the
   SAME lowest price, the FIRST offer in array order wins — the iteration only
   replaces `best` on a strict `<`. This is stable and deterministic: it never
   depends on prices alone, so the single "Best price" marker is always unique
   for a given offer list.
*/
export function bestOffer(offers) {
  let best = null;
  for (const offer of offers) {
    if (!isValidOffer(offer)) continue;
    if (best == null || toPrice(offer.price_value) < toPrice(best.price_value)) {
      best = offer;
    }
  }
  return best;
}

/* Price difference between an offer and the best (lowest) valid offer, in
   rupees.  Returns a number ONLY when both prices are valid; ties yield 0;
   a missing/invalid price on either side yields null (never guessed). */
export function priceDifference(best, offer) {
  const bestPrice = best ? toPrice(best.price_value) : null;
  const offerPrice = offer ? toPrice(offer.price_value) : null;
  if (bestPrice == null || offerPrice == null) return null;
  return offerPrice - bestPrice;
}

export const COMPARE_SORTS = [
  { value: "best-first", label: "Best price first" },
  { value: "price-asc", label: "Price: Low to High" },
  { value: "price-desc", label: "Price: High to Low" },
];

/* Deterministic offer sort for the comparison panel.  Invalid offers are
   excluded (they never appear); the rest are ordered by (price, platform,
   original index).  Ties resolve deterministically — lower price first, then
   platform name alphabetically, then the offer's original array position. */
export function sortOffers(offers, mode = "best-first") {
  const valid = validOffers(offers);
  const indexed = valid.map((offer, i) => ({ offer, i }));
  const priceOf = (o) => toPrice(o.price_value);
  indexed.sort((a, b) => {
    const pa = priceOf(a.offer);
    const pb = priceOf(b.offer);
    if (pa !== pb) return mode === "price-desc" ? pb - pa : pa - pb;
    const byPlatform = String(a.offer.platform || "").localeCompare(
      String(b.offer.platform || "")
    );
    if (byPlatform !== 0) return byPlatform;
    return a.i - b.i;
  });
  return indexed.map((x) => x.offer);
}

/* Distinct marketplaces present across the VALID offers of a group, in order
   of first appearance.  Marketplaces with no offers never appear here, so the
   comparison filter can only offer marketplaces that actually have them. */
export function offerPlatforms(offers) {
  const platforms = [];
  for (const offer of validOffers(offers)) {
    if (offer.platform && !platforms.includes(offer.platform)) {
      platforms.push(offer.platform);
    }
  }
  return platforms;
}

/* Optional original/full price (mrp) supplied by the backend for an offer.

   Returns a numeric MRP ONLY when the backend provides one that is strictly
   greater than the offer's current price.  Anything else returns null so the
   UI can never invent a "strikethrough price" or a discount.
*/
export function mrpForOffer(offer) {
  if (!isValidOffer(offer)) return null;
  const raw =
    offer.mrp ??
    offer.original_price ??
    offer.original_price_value ??
    offer.strike_price;
  const value = toPrice(raw);
  const current = toPrice(offer.price_value);
  if (value == null || current == null || value <= current) return null;
  return value;
}

/* Savings derived ONLY from a valid backend-supplied MRP. Returns null when
   there is nothing mathematically valid to show. */
export function savingsForOffer(offer) {
  const mrp = mrpForOffer(offer);
  const current = toPrice(offer.price_value);
  if (mrp == null || current == null) return null;
  const saved = mrp - current;
  const percent = Math.round((saved / mrp) * 100);
  return { mrp, current, saved, percent };
}

/* Human-facing availability, shown ONLY when the backend says something. */
export function availabilityForOffer(offer) {
  if (!offer) return null;
  if (offer.in_stock === false || offer.is_available === false) {
    return { label: "Out of stock", tone: "out" };
  }
  if (typeof offer.availability === "string" && offer.availability.trim()) {
    return { label: offer.availability.trim(), tone: "text" };
  }
  if (offer.in_stock === true || offer.is_available === true) {
    return { label: "In stock", tone: "in" };
  }
  return null;
}

/* Can a card be rendered as a comparison at all? True when it has ≥1 valid
   offer (a group with no real offers is shown as an honest sub-state). */
export function cardHasValidOffer(card) {
  return Array.isArray(card?.offers) && validOffers(card.offers).length > 0;
}

/* Format a numeric price as INR (used for backend-supplied MRP amounts,
   which arrive numeric; current prices come pre-formatted in price_display). */
export function formatPrice(value) {
  const n = toPrice(value);
  if (n == null) return "";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(n);
}