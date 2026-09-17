import { useEffect, useId, useMemo, useRef, useState } from "react";
import { bestOffer, formatPrice, validOffers } from "../lib/deals.js";
import {
  fetchPriceHistories,
  historySummaries,
  historySummary,
  formatHistoryDate,
  uniqProductKeys,
} from "../lib/priceHistory.js";
import { storeMeta } from "../lib/storeMeta.js";
import PriceHistoryChart from "./PriceHistoryChart";

/* Focus targets inside the dialog for the simple focus trap. */
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
].join(",");

function HistorySeriesRow({ series }) {
  const meta = storeMeta(series.platform);
  return (
    <li className="history-store-row">
      <span
        className="store-avatar"
        style={{ backgroundColor: meta.color, color: meta.text }}
        aria-hidden="true"
      >
        {meta.initials}
      </span>
      <div className="history-store-name">
        <span className="platform-name">{series.platform}</span>
        {series.title && <span className="history-store-title">{series.title}</span>}
      </div>
      <div className="history-store-stat">
        <span className="history-stat-value">{formatPrice(series.stats.low)}</span>
        <span className="history-stat-label">Lowest recorded</span>
      </div>
      <div className="history-store-stat">
        <span className="history-stat-value">{formatPrice(series.stats.high)}</span>
        <span className="history-stat-label">Highest recorded</span>
      </div>
      <div className="history-store-stat">
        <span className="history-stat-value">{series.stats.count}</span>
        <span className="history-stat-label">
          {series.stats.count === 1 ? "observation" : "observations"}
        </span>
      </div>
      <div className="history-store-stat">
        <span className="history-stat-value">{formatHistoryDate(series.stats.firstAt)}</span>
        <span className="history-stat-label">First recorded</span>
      </div>
      <div className="history-store-stat">
        <span className="history-stat-value">{formatHistoryDate(series.stats.lastAt)}</span>
        <span className="history-stat-label">Last recorded</span>
      </div>
      <a
        className="btn btn-secondary history-store-cta"
        href={series.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`View this listing on ${series.platform}`}
      >
        View listing
      </a>
    </li>
  );
}

/* Accessible "Price history" modal.  Shows ONLY real, persisted snapshot data
   returned by the read-only backend endpoint; never invents prices, dates or
   observations.  States: loading / available / honest empty / fetch error. */
export default function PriceHistoryPanel({ card, onClose }) {
  const titleId = useId();
  const panelRef = useRef(null);
  const closeRef = useRef(null);

  const groupOffers = useMemo(
    () => validOffers(card?.offers),
    [card]
  );
  const keys = useMemo(() => uniqProductKeys(groupOffers), [groupOffers]);
  const best = bestOffer(groupOffers);

  const [state, setState] = useState({
    status: keys.length ? "loading" : "empty", // loading | done | empty | error
    series: [],
  });

  useEffect(() => {
    const panel = panelRef.current;
    const previousOverflow = document.body.style.overflow;

    closeRef.current?.focus();
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
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

  useEffect(() => {
    if (!keys.length) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    fetchPriceHistories(keys, { signal: controller.signal })
      .then((offers) => {
        if (cancelled) return;
        const series = historySummaries(offers);
        setState({ status: series.length ? "done" : "empty", series });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error", series: [] });
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [keys]);

  const summary = historySummary(state.series);

  return (
    <div className="compare-overlay" onClick={() => onClose()}>
      <div
        className="compare-dialog history-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={panelRef}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="compare-header">
          <div className="compare-header-text">
            <p className="compare-kicker">Price history</p>
            <h2 id={titleId} className="compare-title">
              {card?.title || ""}
            </h2>
          </div>
          <button
            type="button"
            className="compare-close"
            ref={closeRef}
            onClick={onClose}
            aria-label="Close price history"
          >
            ✕
          </button>
        </header>

        {state.status === "loading" && (
          <div className="history-state" role="status" aria-busy="true" aria-live="polite">
            <span className="history-spinner" aria-hidden="true" />
            <p>Loading price history…</p>
            <div className="history-skeleton" aria-hidden="true">
              <div />
              <div />
              <div />
            </div>
          </div>
        )}

        {state.status === "error" && (
          <div className="history-state">
            <h3 className="history-state-title">Price history is unavailable right now</h3>
            <p className="history-state-hint">
              We couldn’t load the recorded prices for this product. Please try again
              shortly — no price was guessed.
            </p>
          </div>
        )}

        {state.status === "empty" && (
          <div className="history-state">
            {best && (
              <p className="history-current">
                Current lowest price:{" "}
                <strong>{best.price_display}</strong> on {best.platform}
              </p>
            )}
            <h3 className="history-state-title">Price history is not available yet.</h3>
            <p className="history-state-hint">
              DealCompare records a product’s price each time it is observed. Once this
              product has been seen over time, its price trend will appear here.
            </p>
          </div>
        )}

        {state.status === "done" && (
          <div className="history-body">
            {best && (
              <p className="history-current">
                Current lowest price:{" "}
                <strong>{best.price_display}</strong> on {best.platform}
              </p>
            )}

            {summary && (
              <ul className="history-summary" aria-label="Price history summary">
                <li>
                  <span className="history-stat-value">{formatPrice(summary.low)}</span>
                  <span className="history-stat-label">Lowest recorded</span>
                </li>
                <li>
                  <span className="history-stat-value">{formatPrice(summary.high)}</span>
                  <span className="history-stat-label">Highest recorded</span>
                </li>
                <li>
                  <span className="history-stat-value">{summary.count}</span>
                  <span className="history-stat-label">
                    {summary.count === 1 ? "observation" : "observations"}
                  </span>
                </li>
                <li>
                  <span className="history-stat-value">
                    {formatHistoryDate(summary.firstAt)}
                  </span>
                  <span className="history-stat-label">First recorded</span>
                </li>
                <li>
                  <span className="history-stat-value">
                    {formatHistoryDate(summary.lastAt)}
                  </span>
                  <span className="history-stat-label">Last recorded</span>
                </li>
              </ul>
            )}

            <PriceHistoryChart series={state.series} title={card?.title || ""} />

            <ul className="history-stores" aria-label="Price history per marketplace">
              {state.series.map((series) => (
                <HistorySeriesRow
                  key={`${series.platform}-${series.productKey}`}
                  series={series}
                />
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}