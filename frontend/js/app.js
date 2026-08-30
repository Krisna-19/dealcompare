const searchInput = document.getElementById("searchInput");
const searchButton = document.getElementById("searchButton");
const resultsSection = document.getElementById("resultsSection");
const resultsContainer = document.getElementById("results");
const loading = document.getElementById("loading");
const error = document.getElementById("error");
const sortSelect = document.getElementById("sortSelect");
const storeFilters = document.getElementById("storeFilters");
const noFilterResults = document.getElementById("noFilterResults");
const noResults = document.getElementById("noResults");

const API_BASE = "http://127.0.0.1:8000";

let allProducts = [];
let activeStore = "all";

async function searchProducts() {
    const query = searchInput.value.trim();
    if (!query) {
        alert("Please enter a product name.");
        return;
    }
    resultsContainer.innerHTML = "";
    resultsSection.classList.add("hidden");
    error.classList.add("hidden");
    noFilterResults.classList.add("hidden");
    noResults.classList.add("hidden");
    loading.classList.remove("hidden");
    try {
        const response = await fetch(
            `${API_BASE}/search?query=${encodeURIComponent(query)}`
        );
        if (!response.ok) {
            throw new Error("API request failed");
        }
        const data = await response.json();
        allProducts = deduplicateProducts(data.results || []);
        activeStore = "all";
        resetStoreButtons();
        sortSelect.value = "best-deal";
        renderProducts();
    } catch (err) {
        console.error(err);
        error.textContent = "Unable to get product results. Make sure the API server is running.";
        error.classList.remove("hidden");
    } finally {
        loading.classList.add("hidden");
    }
}

function deduplicateProducts(products) {
    const seen = new Map();
    const deduped = [];

    for (const product of products) {
        const key = (product.best_url || "").replace(/[?#].*$/, "").toLowerCase();
        if (key && seen.has(key)) {
            continue;
        }
        if (key) {
            seen.set(key, true);
        }
        deduped.push(product);
    }

    return deduped;
}

function getProductImage(product) {
    if (product.offers && product.offers.length > 0) {
        for (const offer of product.offers) {
            if (offer.image) return offer.image;
        }
    }
    return null;
}

function getBestPriceValue(product) {
    if (product.offers && product.offers.length > 0) {
        let lowest = Infinity;
        for (const offer of product.offers) {
            if (offer.price_value && offer.price_value > 0 && offer.price_value < lowest) {
                lowest = offer.price_value;
            }
        }
        return lowest === Infinity ? null : lowest;
    }
    return null;
}

function getFilteredProducts() {
    if (activeStore === "all") {
        return allProducts;
    }
    // Store filtering operates on OFFERS: a canonical product card stays
    // intact as long as it has any offer from the selected store. It must
    // never split a card into two products.
    return allProducts.filter(function (p) {
        return (p.offers || []).some(function (offer) {
            return offer && offer.platform === activeStore;
        });
    });
}

function deduplicateVisibleOffers(offers) {
    if (!Array.isArray(offers)) {
        return [];
    }
    const seen = new Set();
    const unique = [];
    for (const offer of offers) {
        if (!offer) continue;
        const store = String(offer.platform || "").toLowerCase();
        const price = Number(offer.price_value);
        const title = String(offer.title || "").trim().toLowerCase();
        const key = store + "|" + price + "|" + title;
        if (seen.has(key)) {
            continue;
        }
        seen.add(key);
        unique.push(offer);
    }
    return unique;
}

function getCardOffers(product) {
    if (!Array.isArray(product.offers)) {
        return [];
    }
    let offers = product.offers;
    if (activeStore !== "all") {
        offers = offers.filter(function (offer) {
            return offer && offer.platform === activeStore;
        });
    }
    return deduplicateVisibleOffers(offers);
}

function getBestOffer(product) {
    const offers = getCardOffers(product);
    let best = null;
    for (const offer of offers) {
        const val = Number(offer && offer.price_value);
        if (val > 0 && (!best || val < Number(best.price_value))) {
            best = offer;
        }
    }
    return best;
}

function getEffectiveBestPrice(product) {
    // The price used for sorting and the Best Deal badge must match the
    // price actually shown on the card. Under a store filter that is the
    // filtered best offer (getBestOffer already respects activeStore), NOT
    // the minimum across every store in the card. Using the unfiltered
    // minimum made the sort order and badge contradict the visible prices.
    const best = getBestOffer(product);
    return best ? Number(best.price_value) : null;
}

function normalizeUrl(url, platform) {
    if (!url || typeof url !== "string") return null;
    const trimmed = url.trim();
    if (/^https?:\/\//i.test(trimmed) && trimmed.length > 10) {
        return trimmed;
    }
    if (trimmed.indexOf("//") === 0 && trimmed.length > 10) {
        return "https:" + trimmed;
    }
    if (trimmed.indexOf("/") === 0 && trimmed.length > 5) {
        const base =
            platform && /flipkart/i.test(String(platform))
                ? "https://www.flipkart.com"
                : null;
        return base ? base + trimmed : null;
    }
    return null;
}

function formatPrice(offer) {
    if (offer) {
        const val = Number(offer.price_value);
        if (val > 0) {
            return "\u20b9" + Math.round(val).toLocaleString("en-IN");
        }
        if (offer.price_display && typeof offer.price_display === "string" && offer.price_display.trim()) {
            return offer.price_display.trim();
        }
    }
    return "Check price";
}

function buildOfferButton(offer) {
    const target = offer ? normalizeUrl(offer.url, offer.platform) : null;
    if (target) {
        return '<a class="offer-button" href="' + escapeHtml(target) + '" target="_blank" rel="noopener noreferrer">View Deal</a>';
    }
    return '<span class="offer-button disabled">View Deal</span>';
}

function getVariantText(offer, groupTitle) {
    if (!offer || typeof offer.title !== "string" || !offer.title.trim()) {
        return "";
    }
    const title = offer.title.trim();
    if (typeof groupTitle !== "string" || !groupTitle.trim()) {
        return title;
    }
    const base = groupTitle.trim();

    // The variant label is the tail of the offer's real title after the
    // shared product-family prefix (colour / RAM / storage / model etc).
    // Never invented: always a slice of the actual backend title.
    const a = base.split(/\s+/);
    const b = title.split(/\s+/);
    let i = 0;
    while (i < a.length && i < b.length && a[i] === b[i]) {
        i += 1;
    }
    return b.slice(i).join(" ").trim();
}

function buildOffersHtml(product) {
    const offers = getCardOffers(product);
    if (offers.length === 0) {
        return "";
    }

    const bestOffer = getBestOffer(product);
    const minVal = bestOffer ? Number(bestOffer.price_value) : null;

    let html = '<div class="offer-section">' +
        '<div class="offer-count">' +
            (offers.length === 1 ? "1 offer" : offers.length + " offers") +
        '</div>' +
        '<div class="offer-list">';
    for (let k = 0; k < offers.length; k++) {
        const offer = offers[k];
        if (!offer) continue;

        const platform = offer.platform || "Unknown Store";
        // Every offer tying the lowest price gets the Lowest badge.
        const isCheapest = minVal !== null && Number(offer.price_value) === minVal;
        let rowClass = "offer-row";
        if (isCheapest) rowClass += " cheapest";

        const variant = getVariantText(offer, product.title);

        html += '<div class="' + rowClass + '">' +
            '<div class="offer-line">' +
                '<span class="offer-platform">' + escapeHtml(platform) + '</span>' +
                '<span class="offer-price">' + escapeHtml(formatPrice(offer)) + '</span>' +
                (isCheapest ? '<span class="offer-lowest-tag">Lowest</span>' : '') +
                buildOfferButton(offer) +
            '</div>' +
            (variant ? '<div class="offer-variant">' + escapeHtml(variant) + '</div>' : '') +
            '</div>';
    }
    html += '</div></div>';
    return html;
}

function getSortedProducts(products) {
    const mode = sortSelect.value;
    const sorted = products.slice();

    if (mode === "low-price") {
        sorted.sort(function (a, b) {
            return (getEffectiveBestPrice(a) || Infinity) - (getEffectiveBestPrice(b) || Infinity);
        });
    } else if (mode === "high-price") {
        sorted.sort(function (a, b) {
            return (getEffectiveBestPrice(b) || 0) - (getEffectiveBestPrice(a) || 0);
        });
    } else {
        sorted.sort(function (a, b) {
            return (getEffectiveBestPrice(a) || Infinity) - (getEffectiveBestPrice(b) || Infinity);
        });
    }

    return sorted;
}

function renderProducts() {
    resultsSection.classList.remove("hidden");
    resultsContainer.innerHTML = "";
    noFilterResults.classList.add("hidden");
    noResults.classList.add("hidden");

    const filtered = getFilteredProducts();

    if (filtered.length === 0) {
        if (allProducts.length > 0) {
            noFilterResults.classList.remove("hidden");
        } else {
            noResults.classList.remove("hidden");
        }
        return;
    }

    const sorted = getSortedProducts(filtered);

    let lowestPrice = Infinity;
    for (var i = 0; i < sorted.length; i++) {
        var effectivePrice = getEffectiveBestPrice(sorted[i]);
        if (effectivePrice !== null && effectivePrice < lowestPrice) {
            lowestPrice = effectivePrice;
        }
    }

    for (var j = 0; j < sorted.length; j++) {
        var product = sorted[j];
        var price = getEffectiveBestPrice(product);
        var isBestDeal = price !== null && price === lowestPrice && sorted.length > 1;
        var image = getProductImage(product);
        var bestOffer = getBestOffer(product);

        // When a store filter is active, the card's headline price and store
        // label follow the filtered best offer so the card never advertises
        // a hidden store's price.
        var abPrice = bestOffer ? formatPrice(bestOffer) : (product.best_price || "Check price");
        var abPlatform = bestOffer ? bestOffer.platform : (product.best_platform || "Store");

        var card = document.createElement("div");
        card.className = "product-card" + (isBestDeal ? " best-deal" : "");

        var imageHtml = image
            ? '<img class="card-image" src="' + escapeHtml(image) + '" alt="' + escapeHtml(product.title) + '" onerror="this.outerHTML=\'<div class=\\\'card-image-placeholder\\\' >No image available</div>\'">'
            : '<div class="card-image-placeholder">No image available</div>';

        card.innerHTML =
            '<div class="best-deal-badge">Best Deal</div>' +
            imageHtml +
            '<div class="card-body">' +
                '<div class="card-title">' + escapeHtml(product.title) + '</div>' +
                '<div class="best-price-block">' +
                    '<div class="best-price-label">Best Price</div>' +
                    '<div class="card-price-row">' +
                        '<span class="best-price">' + escapeHtml(abPrice) + '</span>' +
                        '<span class="platform">on ' + escapeHtml(abPlatform) + '</span>' +
                    '</div>' +
                '</div>' +
                buildOffersHtml(product) +
            '</div>';

        resultsContainer.appendChild(card);
    }
}

function resetStoreButtons() {
    var buttons = storeFilters.querySelectorAll(".store-btn");
    for (var i = 0; i < buttons.length; i++) {
        buttons[i].classList.remove("active");
        if (buttons[i].getAttribute("data-store") === "all") {
            buttons[i].classList.add("active");
        }
    }
}

function escapeHtml(text) {
    if (!text) return "";
    var div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
}

searchButton.addEventListener("click", searchProducts);
searchInput.addEventListener("keypress", function (event) {
    if (event.key === "Enter") {
        searchProducts();
    }
});

sortSelect.addEventListener("change", function () {
    if (allProducts.length > 0) {
        renderProducts();
    }
});

storeFilters.addEventListener("click", function (event) {
    var btn = event.target.closest(".store-btn");
    if (!btn) return;

    var buttons = storeFilters.querySelectorAll(".store-btn");
    for (var i = 0; i < buttons.length; i++) {
        buttons[i].classList.remove("active");
    }
    btn.classList.add("active");

    activeStore = btn.getAttribute("data-store");
    if (allProducts.length > 0) {
        renderProducts();
    }
});

// Test hooks (Node only; ignored in the browser).
if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        getCardOffers: getCardOffers,
        getBestPriceValue: getBestPriceValue,
        getBestOffer: getBestOffer,
        getEffectiveBestPrice: getEffectiveBestPrice,
        getFilteredProducts: getFilteredProducts,
        getSortedProducts: getSortedProducts,
        getVariantText: getVariantText,
        deduplicateVisibleOffers: deduplicateVisibleOffers,
        buildOffersHtml: buildOffersHtml,
        normalizeUrl: normalizeUrl,
        formatPrice: formatPrice,
        _setActiveStore: function (store) {
            activeStore = store;
        },
        _setProducts: function (products) {
            allProducts = products;
        },
    };
}
