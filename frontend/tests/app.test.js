// Frontend regression tests for app.js (store filtering, sorting, visible
// offer deduplication, single Lowest tag, variant labels, View Deal URLs).
// Run with:  node frontend/tests/app.test.js
"use strict";

const assert = require("assert");
const path = require("path");

function escapeHtmlPlain(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

let idCounter = 0;

function makeEl(id) {
    const el = {
        _id: id || "el-" + idCounter++,
        _text: "",
        value: "",
        innerHTML: "",
        className: "",
        style: {},
        children: [],
        classList: {
            add() {},
            remove() {},
            contains() {
                return false;
            },
        },
        addEventListener() {},
        appendChild() {},
        querySelectorAll() {
            return [];
        },
        querySelector() {
            return null;
        },
        closest() {
            return null;
        },
        getAttribute() {
            return null;
        },
        setAttribute() {},
    };
    Object.defineProperty(el, "textContent", {
        get() {
            return el._text;
        },
        set(value) {
            el._text = String(value);
            el.innerHTML = escapeHtmlPlain(el._text);
        },
    });
    return el;
}

const elements = {};
global.document = {
    getElementById(id) {
        if (!elements[id]) {
            elements[id] = makeEl(id);
        }
        return elements[id];
    },
    createElement() {
        return makeEl("");
    },
};

const appJs = path.join(__dirname, "..", "js", "app.js");
const app = require(appJs);

function offer(platform, price, title, url) {
    return {
        title,
        product_key: "samsung-s24",
        platform,
        price_value: price,
        price_display: "\u20b9" + price,
        url,
    };
}

const s24ExynosOffers = [
    offer("Flipkart", 55999, "Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)", "/samsung-galaxy-s24-exynos-5g-amber-yellow-256-gb/p/itm1?pid=MOBGX2F3TYAVSQJC"),
    offer("Flipkart", 55999, "Samsung Galaxy S24 5G Snapdragon (Cobalt Violet, 256 GB)", "/samsung-galaxy-s24-5g-snapdragon-cobalt-violet-256-gb/p/itm2?pid=MOBHDVFKKYGS2K9T"),
    offer("Flipkart", 55999, "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 256 GB)", "/samsung-galaxy-s24-5g-snapdragon-onyx-black-256-gb/p/itm3?pid=MOBHDVFKVGGGHBDX"),
    offer("Flipkart", 55999, "Samsung Galaxy S24 5G Snapdragon (Marble Gray, 256 GB)", "/samsung-galaxy-s24-5g-snapdragon-marble-gray-256-gb/p/itm4?pid=MOBHDVFKAWDVHJTU"),
    offer("Flipkart", 55999, "Samsung Galaxy S24 5G Snapdragon (Amber Yellow, 256 GB)", "/samsung-galaxy-s24-5g-snapdragon-amber-yellow-256-gb/p/itm5?pid=MOBHDVFKDNDVPYMK"),
    offer("Flipkart", 55999, "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 256 GB)", "/samsung-galaxy-s24-5g-snapdragon-onyx-black-256-gb/p/itm7?pid=MOBHDVFREPEATED"),
    offer("Flipkart", 75999, "Samsung Galaxy S24 Exynos 5G (Marble Gray, 256 GB)", "/samsung-galaxy-s24-exynos-5g-marble-gray-256-gb/p/itm6?pid=MOBH5TKXJBNXDGRE"),
];

const s24ExynosProduct = {
    title: "Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)",
    best_price: "\u20b955,999",
    best_platform: "Flipkart",
    best_url: "/samsung-galaxy-s24-exynos-5g-amber-yellow-256-gb/p/itm1?pid=MOBGX2F3TYAVSQJC",
    offers: s24ExynosOffers,
};

app._setActiveStore("all");
const cardOffers = app.getCardOffers(s24ExynosProduct);

// 1. visible deduplication: two 'Snapdragon (Onyx Black, 256 GB)' rows
//    with different pids but the same store/price/title collapse; the
//    distinct variants survive.
assert.strictEqual(cardOffers.length, 6, "identical-looking rows must collapse, distinct variants survive");
const keys = cardOffers.map((o) =>
    String(o.platform).toLowerCase() + "|" + Number(o.price_value) + "|" + String(o.title).trim().toLowerCase()
);
assert.strictEqual(new Set(keys).size, 6, "all retained rows are visibly distinct");
assert.ok(cardOffers.some((o) => o.title.indexOf("Cobalt Violet") !== -1), "distinct colour variant retained");
assert.ok(cardOffers.some((o) => o.title.indexOf("Onyx Black") !== -1), "distinct colour variant retained");

// 2. 'Lowest' appears on every offer tying the lowest price: after visible
//    dedup the card holds 6 offers, 5 of them at the 55999 low -> 5 tags.
const html = app.buildOffersHtml(s24ExynosProduct);
assert.strictEqual(
    (html.match(/Lowest/g) || []).length,
    5,
    "every tied-lowest offer must get the Lowest badge"
);
assert.ok(html.indexOf("6 offers") !== -1, "offer count label reflects the visible offers");

// 3. variant labels expose the real difference from the backend title.
assert.ok(html.indexOf("Snapdragon (Cobalt Violet, 256 GB)") !== -1, "variant label for Cobalt Violet shown");
assert.ok(html.indexOf("(Marble Gray, 256 GB)") !== -1, "variant label for Marble Gray shown");

// 4. each offer row keeps its View Deal URL (flipkart relative -> absolute).
const hrefs = (html.match(/href="([^"]*)"/g) || []).map((h) => h.slice(6, -1));
assert.strictEqual(hrefs.length, 6, "one View Deal link per unique offer row");
for (const href of hrefs) {
    assert.ok(/^https:\/\/www\.flipkart\.com\//.test(href), "View Deal URL normalized to absolute: " + href);
}
assert.ok(
    hrefs.some((h) => h.indexOf("MOBGX2F3TYAVSQJC") !== -1),
    "View Deal URL belongs to the retained offer"
);

// 5. cheapest offer is the retained first-min row.
assert.strictEqual(app.getBestPriceValue(s24ExynosProduct), 55999, "cheapest value");
assert.strictEqual(app.getBestOffer(s24ExynosProduct).url, s24ExynosOffers[0].url, "cheapest offer is retained");

// 6. store filtering (offer level).
app._setActiveStore("Amazon");
const amazonOffers = [
    offer("Amazon", 58799, "Galaxy S24 5G AI Smartphone (Onyx Black, 8GB, 256GB Storage)", "https://www.amazon.in/dp/B0CS69QQTG"),
    offer("Flipkart", 55999, "Samsung Galaxy S24 Exynos 5G (Amber Yellow, 256 GB)", "/samsung-galaxy-s24-exynos-5g-amber-yellow-256-gb/p/itm1?pid=MOBGX2F3TYAVSQJC"),
];
const multiStoreProduct = { title: "Samsung Galaxy S24", offers: amazonOffers };
assert.deepStrictEqual(
    app.getCardOffers(multiStoreProduct).map((o) => o.platform),
    ["Amazon"],
    "store filter keeps only the active store's offers"
);
assert.ok(
    app.buildOffersHtml(multiStoreProduct).indexOf("Flipkart") === -1,
    "hidden store's offers are not rendered"
);
app._setActiveStore("all");

// 7. store filtering (card level).
const cards = [
    {
        title: "A",
        best_platform: "Flipkart",
        offers: [offer("Flipkart", 100, "A", "/a?pid=AA")],
    },
    {
        title: "B",
        best_platform: "Amazon",
        offers: [offer("Amazon", 200, "B", "https://www.amazon.in/dp/B0CS69QQTG")],
    },
];
app._setProducts(cards);
app._setActiveStore("all");
assert.strictEqual(app.getFilteredProducts().length, 2, "All Stores shows every card");
app._setActiveStore("Flipkart");
assert.deepStrictEqual(
    app.getFilteredProducts().map((p) => p.best_platform),
    ["Flipkart"],
    "store filter at card level"
);

// 7b. canonical multi-store card: the store filter acts on OFFERS and must
//     never split one canonical SKU into two product cards.
const canonicalCard = {
    title: "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
    best_price: "\u20b949,999",
    best_platform: "Flipkart",
    best_url: "/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/itx?pid=FKONYX",
    offers: [
        offer("Flipkart", 49999, "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)", "/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/itx?pid=FKONYX"),
        offer("Amazon", 54499, "Galaxy S24 Snapdragon 8 Gen 3 5G (Onyx Black, 128 GB) (8 GB RAM)", "https://www.amazon.in/dp/B0ONYXS24"),
    ],
};
app._setProducts([canonicalCard]);
app._setActiveStore("Amazon");
assert.strictEqual(app.getFilteredProducts().length, 1, "Amazon filter keeps the canonical card");
assert.strictEqual(app.getBestOffer(canonicalCard).platform, "Amazon", "filtered best offer is Amazon");
assert.strictEqual(app.getBestOffer(canonicalCard).price_value, 54499, "filtered best price is the Amazon offer");
assert.deepStrictEqual(
    app.getCardOffers(canonicalCard).map((o) => o.platform),
    ["Amazon"],
    "offer-level filtering under the store filter"
);
assert.ok(
    app.buildOffersHtml(canonicalCard).indexOf("Flipkart") === -1,
    "hidden store's offer is not rendered under the filter"
);
app._setActiveStore("all");
assert.strictEqual(app.getCardOffers(canonicalCard).length, 2, "All Stores shows both offers");
assert.strictEqual(
    (app.buildOffersHtml(canonicalCard).match(/Lowest/g) || []).length,
    1,
    "one Lowest tag per canonical card"
);
assert.strictEqual(app.getBestPriceValue(canonicalCard), 49999, "best value across both stores");

// 7c. tied-lowest across stores: same price on Amazon AND Flipkart -> BOTH
//     offers carry the Lowest badge; "1 offer" label for a single offer.
const tiedCard = {
    title: "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
    offers: [
        offer("Amazon", 49999, "Galaxy S24 Snapdragon 8 Gen 3 5G (Onyx Black, 128 GB) (8 GB RAM)", "https://www.amazon.in/dp/B0TIEDAMZ"),
        offer("Flipkart", 49999, "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)", "/samsung-galaxy-s24-5g-snapdragon-onyx-black-128-gb/p/itx?pid=FKTIED"),
    ],
};
const tiedHtml = app.buildOffersHtml(tiedCard);
assert.strictEqual(app.getBestPriceValue(tiedCard), 49999, "tied lowest value");
assert.strictEqual(
    (tiedHtml.match(/Lowest/g) || []).length,
    2,
    "all tied-lowest offers get the Lowest badge"
);
assert.strictEqual(app.getBestOffer(tiedCard).platform, "Amazon", "first tied offer is the best referent");
assert.strictEqual(tiedHtml.indexOf("2 offers") !== -1 ? "2 offers" : tiedHtml, "2 offers", "two-offer count label");
assert.strictEqual(
    app.buildOffersHtml({
        title: "Single",
        offers: [offer("Flipkart", 49999, "Single", "/single/p/itx?pid=ONLY")],
    }).indexOf("1 offer") !== -1,
    true,
    "singular offer count label"
);

// 8. sorting: Best Deal / Lowest / Highest.
app._setActiveStore("all");
elements["sortSelect"].value = "low-price";
assert.deepStrictEqual(
    app.getSortedProducts(cards).map((p) => app.getBestPriceValue(p)),
    [100, 200],
    "lowest price sort ascending"
);
elements["sortSelect"].value = "high-price";
assert.deepStrictEqual(
    app.getSortedProducts(cards).map((p) => app.getBestPriceValue(p)),
    [200, 100],
    "highest price sort descending"
);
elements["sortSelect"].value = "best-deal";
assert.deepStrictEqual(
    app.getSortedProducts(cards).map((p) => app.getBestPriceValue(p)),
    [100, 200],
    "best deal = ascending"
);

// 8b. Case I: sorting and the Best Deal badge must use the FILTERED best
//     offer price, consistent with the price shown on the card. A card
//     whose cheapest offer is hidden by the store filter must NOT outrank
//     a card whose visible price is lower.
function mkOffer(platform, price, url) {
    return { title: "X", product_key: "s24", platform, price_value: price, price_display: "\u20b9" + price, url };
}
const sortCardHidden = {
    title: "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
    offers: [
        mkOffer("Amazon", 54499, "https://www.amazon.in/dp/BX"),
        mkOffer("Flipkart", 49999, "/hidden/p?pid=FKX"),
    ],
};
const sortCardVisibleLow = {
    title: "Samsung Galaxy S24 5G Snapdragon (Onyx Black, 128 GB)",
    offers: [mkOffer("Amazon", 50000, "https://www.amazon.in/dp/BY")],
};
app._setProducts([sortCardHidden, sortCardVisibleLow]);
app._setActiveStore("Amazon");
elements["sortSelect"].value = "low-price";
const amazonSorted = app.getSortedProducts(app.getFilteredProducts());
assert.strictEqual(
    app.getEffectiveBestPrice(amazonSorted[0]),
    50000,
    "under Amazon filter the lowest VISIBLE price sorts first (hidden Flipkart 49999 excluded)"
);
assert.strictEqual(
    app.getEffectiveBestPrice(sortCardHidden),
    54499,
    "effective best price respects the active store filter"
);
app._setActiveStore("all");
assert.strictEqual(
    app.getEffectiveBestPrice(sortCardHidden),
    49999,
    "All Stores effective best price is the global minimum of the card"
);
assert.strictEqual(
    app.getEffectiveBestPrice(sortCardVisibleLow),
    50000,
    "All Stores effective best price for the single-offer card"
);
app._setActiveStore("all");

// 9. URL normalization helpers still behave.
assert.strictEqual(
    app.normalizeUrl("/samsung-galaxy-s24-5g/p/itm1?pid=MOBX", "Flipkart"),
    "https://www.flipkart.com/samsung-galaxy-s24-5g/p/itm1?pid=MOBX"
);
assert.strictEqual(app.normalizeUrl("https://www.amazon.in/dp/B0CS69QQTG", "Amazon"), "https://www.amazon.in/dp/B0CS69QQTG");
assert.strictEqual(app.normalizeUrl("", "Flipkart"), null);

console.log("app.test.js: all frontend regression checks passed");