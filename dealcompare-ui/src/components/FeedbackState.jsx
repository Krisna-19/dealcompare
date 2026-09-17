/* Shared feedback UI: idle/empty/error/filter panels and the loading skeleton.
   Honest messaging only — never invents products, prices or offers. */

const ICONS = {
  search: (
    <svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true">
      <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  ),
  empty: (
    <svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true">
      <path
        d="M4 7h16l-1.5 12h-13L4 7Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M8 7V6a4 4 0 0 1 8 0v1" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  ),
  error: (
    <svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <line x1="12" y1="8" x2="12" y2="13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="16.5" r="1.1" fill="currentColor" />
    </svg>
  ),
  filter: (
    <svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true">
      <path
        d="M4 6h16M7 12h10M10 18h4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  ),
};

export function FeedbackState({ variant = "empty", title, hint }) {
  return (
    <div className="feedback" role={variant === "error" ? "alert" : "status"}>
      <div className="feedback-icon" aria-hidden="true">
        {ICONS[variant] || ICONS.empty}
      </div>
      <h2 className="feedback-title">{title}</h2>
      {hint && <p className="feedback-hint">{hint}</p>}
    </div>
  );
}

export function LoadingCards({ count = 3 }) {
  return (
    <div
      className="results"
      role="status"
      aria-busy="true"
      aria-label="Searching deals across marketplaces"
    >
      <span className="sr-only">Searching deals, comparing prices…</span>
      {Array.from({ length: count }).map((_, i) => (
        <div className="card skeleton-card" key={i} aria-hidden="true">
          <div className="card-media">
            <div className="skeleton skeleton-img" />
          </div>
          <div className="card-body">
            <div className="skeleton skeleton-line w60" />
            <div className="skeleton skeleton-line w85" />
            <div className="skeleton skeleton-line w40" />
            <div className="skeleton skeleton-line w90" />
            <div className="skeleton skeleton-line w70" />
            <div className="skeleton skeleton-btn" />
          </div>
        </div>
      ))}
    </div>
  );
}