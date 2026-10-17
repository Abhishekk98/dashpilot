import type { Insight } from "@/lib/api";

const W = 360;
const H = 110;

/** Area line chart (trends, anomalies, Pareto curve) with the highlighted point marked. */
function LineChart({ s, dark }: { s: Insight["series"]; dark: boolean }) {
  const values = s.values;
  if (values.length < 2) return null;
  const min = Math.min(...values, 0);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => [10 + (i / (values.length - 1)) * (W - 20), 10 + (1 - (v - min) / span) * (H - 30)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L ${pts[pts.length - 1][0].toFixed(1)} ${H - 20} L ${pts[0][0].toFixed(1)} ${H - 20} Z`;
  const hi = s.highlight ?? values.length - 1;
  const gid = `g-${s.labels.join("").length}-${values.length}-${dark ? "d" : "l"}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Trend chart">
      <defs>
        <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#F8CF4B" stopOpacity={dark ? 0.35 : 0.3} />
          <stop offset="100%" stopColor="#F8CF4B" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke="#F8CF4B" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {pts[hi] && <circle cx={pts[hi][0]} cy={pts[hi][1]} r="5" fill="#F8CF4B" stroke={dark ? "#232323" : "#ffffff"} strokeWidth="2" />}
      <text x="10" y={H - 4} className={`font-code-sm ${dark ? "fill-[#8b8a8a]" : "fill-[#747878]"}`} fontSize="10">
        {s.labels[0]}: {s.texts[0]}
      </text>
      <text x={W - 10} y={H - 4} textAnchor="end" fontSize="10" className={`font-code-sm font-semibold ${dark ? "fill-[#F8CF4B]" : "fill-[#735c00]"}`}>
        {s.labels[hi]}: {s.texts[hi]}
      </text>
    </svg>
  );
}

/** Horizontal bars (performers, alerts, period comparisons). */
function BarList({ s, dark }: { s: Insight["series"]; dark: boolean }) {
  const rows = s.values.slice(0, 5);
  const max = Math.max(...rows.map((v) => Math.abs(v)), 0) || 1;
  return (
    <div className="flex flex-col gap-1.5 font-code-sm text-code-sm">
      {rows.map((v, i) => {
        const hi = i === s.highlight;
        return (
          <div key={`${s.labels[i]}-${i}`} className="grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-2">
            <span className={`truncate ${dark ? "text-on-primary-container" : "text-on-surface-variant"}`} title={s.labels[i]}>
              {s.labels[i]}
            </span>
            <span className={`h-2 rounded-full overflow-hidden ${dark ? "bg-inverse-surface" : "bg-surface-container"}`}>
              <span
                className={`block h-full rounded-full ${hi ? "bg-secondary-container" : dark ? "bg-outline" : "bg-outline-variant"}`}
                style={{ width: `${Math.max(3, (Math.abs(v) / max) * 100)}%` }}
              />
            </span>
            <span className={`${hi ? (dark ? "text-secondary-container" : "text-on-surface font-semibold") : dark ? "text-on-primary-container" : "text-on-surface-variant"}`}>
              {s.texts[i]}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function InsightChart({ insight, dark = false }: { insight: Insight; dark?: boolean }) {
  const s = insight.series;
  if (!s.values.length) return null;
  return s.kind === "bar" ? <BarList s={s} dark={dark} /> : <LineChart s={s} dark={dark} />;
}
