import { formatPrice } from "../lib/deals.js";
import { formatHistoryDate } from "../lib/priceHistory.js";
import { storeMeta } from "../lib/storeMeta.js";

/* Responsive, dependency-free SVG area/line chart for the price-history
   modal.  Draws ONLY the real observations of the supplied series:

   - A series with >= 2 observations is drawn as a line with dots.
   - A series with exactly 1 observation is drawn as a single dot (no line —
     a one-point "trend" would be misleading).
   - The y axis spans min..max of the real prices (padded so dots don't touch
     the frame); the x axis spans first..last real observation time.
   - Nothing is ever interpolated beyond supplied data.
*/

const W = 560;
const H = 220;
const PAD = { top: 16, right: 16, bottom: 30, left: 58 };

export default function PriceHistoryChart({ series, title }) {
  const points = [];
  for (const s of series) {
    for (const o of s.observations) points.push(o);
  }
  if (!points.length) return null;

  const times = points.map((o) => o.observed_at);
  const prices = points.map((o) => o.price_value);
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  let lo = Math.min(...prices);
  let hi = Math.max(...prices);
  if (lo === hi) {
    const pad = Math.max(1, Math.abs(lo) * 0.05);
    lo -= pad;
    hi += pad;
  } else {
    const pad = (hi - lo) * 0.1;
    lo -= pad;
    hi += pad;
  }

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (t) => PAD.left + ((t - t0) / (t1 - t0 || 1)) * plotW;
  const y = (p) => PAD.top + ((hi - p) / (hi - lo)) * plotH;

  const linePath = (obs) =>
    obs
      .map((o, i) =>
        `${i === 0 ? "M" : "L"}${x(o.observed_at).toFixed(1)},${y(o.price_value).toFixed(1)}`
      )
      .join(" ");

  const yTicks = [lo, (lo + hi) / 2, hi];
  const xMid = (t0 + t1) / 2;
  const xTicks = [
    { t: t0, anchor: "start" },
    { t: xMid, anchor: "middle" },
    { t: t1, anchor: "end" },
  ];

  return (
    <div className="history-chart">
      <svg
        className="history-chart-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Price trend for ${title}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line
              className="history-chart-grid"
              x1={PAD.left}
              y1={y(v)}
              x2={W - PAD.right}
              y2={y(v)}
            />
            <text
              className="history-chart-axis"
              x={PAD.left - 8}
              y={y(v) + 4}
              textAnchor="end"
            >
              {formatPrice(v)}
            </text>
          </g>
        ))}

        {xTicks.map(({ t, anchor }) => (
          <text
            key={t}
            className="history-chart-axis"
            x={x(t)}
            y={H - 8}
            textAnchor={anchor}
          >
            {formatHistoryDate(t)}
          </text>
        ))}

        {series.map((s) => {
          const meta = storeMeta(s.platform);
          const hasLine = s.observations.length > 1;
          return (
            <g key={`${s.platform}-${s.productKey}`}>
              {hasLine && (
                <path
                  className="history-chart-line"
                  d={linePath(s.observations)}
                  fill="none"
                  stroke={meta.color}
                  strokeWidth={2.5}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              )}
              {s.observations.map((o, i) => (
                <circle
                  key={`${o.observed_at}-${i}`}
                  cx={x(o.observed_at)}
                  cy={y(o.price_value)}
                  r={hasLine ? 3.5 : 5}
                  fill={meta.color}
                  stroke="#ffffff"
                  strokeWidth={1.5}
                />
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}