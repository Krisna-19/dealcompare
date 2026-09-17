import { useEffect, useMemo, useRef, useState } from "react";
import {
  bestOffer,
  formatPrice,
  savingsForOffer,
  availabilityForOffer,
  isValidOffer,
  validOffers,
} from "../lib/deals.js";
import { storeMeta } from "../lib/storeMeta.js";
import ComparePanel from "./ComparePanel";

/* Card-level image from the API: card.image first, else first offer image. */
function productImage(card, offers) {
  if (typeof card?.image === "string" && card.image) return card.image;
  const first = offers.find((o) => typeof o.image === "string" && o.image);
  return first ? first.image : "";
}

function OfferRow({ offer, isBest }) {
  const meta = storeMeta(offer.platform);
  const savings = savingsForOffer(offer);
  const availability = availabilityForOffer(offer);

  return (
    <div
      className={`offer-row${isBest ? " offer-row-best" : ""}`}
      role="listitem"
    >
      <span
        className="store-avatar"
        style={{ backgroundColor: meta.color, color: meta.text }}
        aria-hidden="true"
      >
        {meta.initials}
      </span>

      <div className="offer-info">
        <span className="platform-name">{offer.platform}</span>
        {availability && (
          <span className={`availability availability-${availability.tone}`}>
            {availability.label}
          </span>
        )}
      </div>

      <div className="offer-price">
        <span className="price">{offer.price_display}</span>
        {savings && (
          <span className="mrp" aria-label={`Original price ${formatPrice(savings.mrp)}`}>
            {formatPrice(savings.mrp)}
          </span>
        )}
      </div>

      <div className="offer-actions">
        {savings && (
          <span className="save-badge">
            Save {formatPrice(savings.saved)} ({savings.percent}%)
          </span>
        )}
        {isBest && (
          <span className="best-chip">
            <span aria-hidden="true">✓ </span>Best price
          </span>
        )}
        {/* Real product URL from the /search API. The frontend never builds,
            guesses or fabricates a deal URL. */}
        <a
          className="btn btn-primary"
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

/* One product group (card) from the backend aggregator.  The backend owns
   grouping/variants; this component only renders what the API returned and
   never re-combines offers across products. */
export default function ProductCard({ card, offers, categoryLabel }) {
  const [compareOpen, setCompareOpen] = useState(false);
  const triggerRef = useRef(null);
  const wasOpen = useRef(false);

  const valid = Array.isArray(offers) ? offers.filter(isValidOffer) : [];
  const best = bestOffer(valid);
  const image = productImage(card, valid);

  /* Full product group from the API (not the home store-filtered view):
     "Compare offers" appears once the GROUP has 2+ valid offers. */
  const groupOffers = useMemo(() => validOffers(card.offers), [card]);
  const canCompare = groupOffers.length >= 2;

  const closeCompare = () => setCompareOpen(false);

  /* Restore keyboard focus to the trigger after the modal closes. */
  useEffect(() => {
    if (wasOpen.current && !compareOpen && triggerRef.current) {
      triggerRef.current.focus();
    }
    wasOpen.current = compareOpen;
  }, [compareOpen]);

  return (
    <article className="card" aria-label={card.title}>
      <div className="card-media">
        {image ? (
          <img
            className="card-image"
            src={image}
            alt={card.title}
            loading="lazy"
            onError={(e) => {
              e.currentTarget.style.display = "none";
              e.currentTarget.parentElement.classList.add("has-image-error");
            }}
          />
        ) : (
          <div className="card-image-placeholder">No image</div>
        )}
      </div>

      <div className="card-body">
        <div className="card-head">
          <div className="card-heading">
            {categoryLabel && <span className="category-badge">{categoryLabel}</span>}
            <h2 className="card-title">{card.title}</h2>
          </div>

          {best && (
            <div className="best-headline">
              <span className="best-headline-label">Best price</span>
              <span className="best-headline-price">{best.price_display}</span>
              <span className="best-headline-store">on {best.platform}</span>
            </div>
          )}
        </div>

        {valid.length === 0 ? (
          <div className="no-valid-offers">
            No valid offers available for this product right now.
          </div>
        ) : (
          <div className="offers" role="list" aria-label={`Offers for ${card.title}`}>
            {valid.map((offer, index) => (
              <OfferRow
                key={`${offer.platform}-${index}`}
                offer={offer}
                isBest={offer === best}
                index={index}
              />
            ))}
          </div>
        )}

        {canCompare && (
          <div className="card-footer">
            <button
              type="button"
              className="btn btn-secondary compare-trigger"
              ref={triggerRef}
              onClick={() => setCompareOpen(true)}
              aria-expanded={compareOpen}
              aria-haspopup="dialog"
              aria-label={`Compare ${groupOffers.length} offers for ${card.title}`}
            >
              Compare {groupOffers.length} offers
            </button>
          </div>
        )}
      </div>

      {compareOpen && <ComparePanel card={card} onClose={closeCompare} />}
    </article>
  );
}