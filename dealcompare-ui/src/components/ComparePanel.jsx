import { useEffect, useMemo, useRef, useState, useId } from "react";
import {
  validOffers,
  bestOffer,
  priceDifference,
  sortOffers,
  offerPlatforms,
  COMPARE_SORTS,
  savingsForOffer,
  availabilityForOffer,
  formatPrice,
} from "../lib/deals.js";
import { storeMeta } from "../lib/storeMeta.js";

const ALL_STORES = "All Stores";

/* Focus targets inside the dialog for the simple focus trap. */
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
].join(",");

/* Offer image: prefer the offer's own image, then the group-level card image.
   Nothing at all -> honest "No image" placeholder. */
function OfferThumb({ offer, fallback }) {
  const src =
    typeof offer.image === "string" && offer.image.trim()
      ? offer.image
      : typeof fallback === "string" && fallback.trim()
        ? fallback
        : "";
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return <div className="compare-thumb compare-thumb-placeholder">No image</div>;
  }
  return (
    <img
      className="compare-thumb"
      src={src}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

function CompareOfferRow({ offer, best, card }) {
  const meta = storeMeta(offer.platform);
  const savings = savingsForOffer(offer);
  const availability = availabilityForOffer(offer);
  const isBest = offer === best;
  const diff = best && !isBest ? priceDifference(best, offer) : null;
  const showTitle = offer.title && offer.title !== card.title ? offer.title : "";

  return (
    <div className={`compare-row${isBest ? " compare-row-best" : ""}`}>
      <div className="compare-thumb-wrap">
        <OfferThumb offer={offer} fallback={card.image} />
      </div>

      <div className="compare-info">
        <span
          className="store-avatar"
          style={{ backgroundColor: meta.color, color: meta.text }}
          aria-hidden="true"
        >
          {meta.initials}
        </span>
        <span className="platform-name">{offer.platform}</span>
        {showTitle && <span className="compare-offer-title">{showTitle}</span>}
        {availability && (
          <span className={`availability availability-${availability.tone}`}>
            {availability.label}
          </span>
        )}
      </div>

      <div className="compare-price-block">
        <span className="compare-price">{offer.price_display}</span>
        {savings && (
          <>
            <span className="mrp">{formatPrice(savings.mrp)}</span>
            <span className="save-badge">
              Save {formatPrice(savings.saved)} ({savings.percent}%)
            </span>
          </>
        )}
      </div>

      <div className="compare-meta">
        {isBest && (
          <span className="best-chip">
            <span aria-hidden="true">✓ </span>Best price
          </span>
        )}
        {diff != null && diff > 0 && (
          <span className="compare-diff">
            +{formatPrice(diff)} more than best
          </span>
        )}
      </div>

      <div className="compare-actions">
        {/* Real product URL from the /search API. The frontend never builds,
            guesses or fabricates a deal URL. */}
        <a
          className="btn btn-primary btn-compare-view"
          href={offer.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`View deal on ${offer.platform} for ${offer.price_display}`}
        >
          View Deal
        </a>
      </div>
    </div>
  );
}

/* Accessible modal that compares every valid offer of one product group.
   Data comes only from the /search API card; nothing is invented here. */
export default function ComparePanel({ card, onClose }) {
  const titleId = useId();
  const panelRef = useRef(null);
  const closeRef = useRef(null);

  const groupOffers = useMemo(() => validOffers(card.offers), [card]);
  const platforms = useMemo(() => offerPlatforms(groupOffers), [groupOffers]);

  const [store, setStore] = useState(ALL_STORES);
  const [sort, setSort] = useState("best-first");

  const scoped =
    store === ALL_STORES
      ? groupOffers
      : groupOffers.filter((o) => o.platform === store);
  const shown = useMemo(() => sortOffers(scoped, sort), [scoped, sort]);
  const best = useMemo(() => bestOffer(shown), [shown]);

  useEffect(() => {
    const panel = panelRef.current;
    const previousOverflow = document.body.style.overflow;

    // Move focus into the dialog and keep page scroll locked while open.
    closeRef.current?.focus();
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel) return;

      // Simple, robust focus trap: cycle within the dialog's own controls.
      const focusables = Array.from(
        panel.querySelectorAll(FOCUSABLE_SELECTOR)
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div
      className="compare-overlay"
      onClick={() => onClose()}
    >
      <div
        className="compare-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={panelRef}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="compare-header">
          <div className="compare-header-text">
            <p className="compare-kicker">Compare offers</p>
            <h2 id={titleId} className="compare-title">
              {card.title}
            </h2>
          </div>
          <button
            type="button"
            className="compare-close"
            ref={closeRef}
            onClick={onClose}
            aria-label="Close comparison"
          >
            ✕
          </button>
        </header>

        <div className="compare-toolbar">
          {platforms.length > 1 && (
            <div className="store-filters" role="group" aria-label="Filter offers by marketplace">
              {[ALL_STORES, ...platforms].map((name) => (
                <button
                  key={name}
                  type="button"
                  className={`store-btn${store === name ? " active" : ""}`}
                  aria-pressed={store === name}
                  onClick={() => setStore(name)}
                >
                  {name}
                </button>
              ))}
            </div>
          )}

          <label className="sort-control">
            <span className="sort-label">Sort</span>
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              aria-label="Sort offers"
            >
              {COMPARE_SORTS.map((mode) => (
                <option key={mode.value} value={mode.value}>
                  {mode.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <p className="compare-count" aria-live="polite">
          {shown.length} {shown.length === 1 ? "offer" : "offers"}
          {store === ALL_STORES && platforms.length > 1
            ? ` across ${platforms.length} marketplaces`
            : ` from ${store}`}
        </p>

        <div className="compare-rows">
          {shown.map((offer, index) => (
            <CompareOfferRow
              key={`${offer.platform}-${index}`}
              offer={offer}
              best={best}
              card={card}
            />
          ))}
        </div>
      </div>
    </div>
  );
}