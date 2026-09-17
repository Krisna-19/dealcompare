import {
  bestOffer,
  formatPrice,
  savingsForOffer,
  availabilityForOffer,
  isValidOffer,
} from "../lib/deals.js";

/* Store identity for the offer rows: a small colored avatar + display name.
   Unknown/new marketplaces degrade to a neutral tone — never hidden. */
const STORE_META = {
  Flipkart: { initials: "FL", color: "#1f6feb", text: "#FFFFFF" },
  Amazon: { initials: "AZ", color: "#ff9900", text: "#0b0b0b" },
  Myntra: { initials: "MY", color: "#ff3f6c", text: "#FFFFFF" },
  Ajio: { initials: "AJ", color: "#111827", text: "#FFFFFF" },
  Croma: { initials: "CR", color: "#1d4ed8", text: "#FFFFFF" },
  "Tata CLiQ": { initials: "TC", color: "#0f766e", text: "#FFFFFF" },
  Meesho: { initials: "MS", color: "#c2410c", text: "#FFFFFF" },
};

function storeMeta(platform) {
  const known = STORE_META[platform];
  if (known) return known;
  const initials = (platform || "ST").slice(0, 2).toUpperCase();
  return { initials, color: "#4b5563", text: "#FFFFFF" };
}

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
  const valid = Array.isArray(offers) ? offers.filter(isValidOffer) : [];
  const best = bestOffer(valid);
  const image = productImage(card, valid);

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
      </div>
    </article>
  );
}