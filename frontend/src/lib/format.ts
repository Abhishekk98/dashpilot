/** Display helpers shared by data screens. */

import type { ColumnProfile, DetectedType, SemanticRole } from "./api";

const nf = new Intl.NumberFormat("en-US");

export const formatNumber = (n: number) => nf.format(n);

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function timeAgo(iso: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function formatPct(n: number, digits = 1): string {
  return `${n.toFixed(digits)}%`;
}

/** Type pill label + colours, following the design's type pills. */
export const TYPE_STYLES: Record<DetectedType, { label: string; pill: string; dot: string; icon: string }> = {
  id: { label: "ID / Key", pill: "bg-surface-container text-on-surface", dot: "bg-primary-container", icon: "tag" },
  uuid: { label: "UUID String", pill: "bg-surface-container text-on-surface", dot: "bg-primary-container", icon: "link" },
  currency: { label: "Currency", pill: "bg-[#E8F0FE] text-[#1967D2]", dot: "bg-[#1967D2]", icon: "attach_money" },
  percentage: { label: "Percentage", pill: "bg-[#E8F0FE] text-[#1967D2]", dot: "bg-[#1967D2]", icon: "percent" },
  integer: { label: "Integer", pill: "bg-[#E8F0FE] text-[#1967D2]", dot: "bg-[#1967D2]", icon: "123" },
  decimal: { label: "Decimal", pill: "bg-[#E8F0FE] text-[#1967D2]", dot: "bg-[#1967D2]", icon: "123" },
  date: { label: "Date", pill: "bg-[#FEF7E0] text-[#B06000]", dot: "bg-[#B06000]", icon: "calendar_today" },
  datetime: { label: "DateTime", pill: "bg-[#FEF7E0] text-[#B06000]", dot: "bg-[#B06000]", icon: "calendar_today" },
  boolean: { label: "Boolean", pill: "bg-surface-container text-on-surface", dot: "bg-primary-container", icon: "toggle_on" },
  email: { label: "Email", pill: "bg-surface-container text-on-surface", dot: "bg-primary-container", icon: "alternate_email" },
  location: { label: "Location", pill: "bg-[#E6F4EA] text-[#137333]", dot: "bg-[#137333]", icon: "location_on" },
  category: { label: "Category", pill: "bg-surface-container text-on-surface", dot: "bg-primary-container", icon: "tune" },
  text: { label: "Text", pill: "bg-surface-container text-on-surface", dot: "bg-primary-container", icon: "notes" },
};

export function typeLabel(col: ColumnProfile): string {
  const base = TYPE_STYLES[col.detected_type].label;
  return col.detected_type === "currency" && col.currency_symbol ? `${base} (${col.currency_symbol})` : base;
}

/** Role pill label, icon and colours, following the design's "AI Semantic Role" pills. */
export const ROLE_STYLES: Record<SemanticRole, { label: string; icon: string; pill: string; iconClass?: string }> = {
  primary_key: { label: "Primary Key", icon: "key", pill: "bg-secondary-container text-on-secondary-fixed font-semibold" },
  foreign_key: { label: "Foreign Key", icon: "share", pill: "bg-secondary-container/40 text-on-secondary-container font-semibold" },
  measure: {
    label: "Measure Candidate",
    icon: "calculate",
    pill: "bg-primary-container text-on-primary font-medium",
    iconClass: "text-secondary-container",
  },
  time_dimension: { label: "Time Dimension", icon: "schedule", pill: "bg-surface-container text-on-surface font-medium" },
  geo_dimension: { label: "Geo Dimension", icon: "map", pill: "bg-surface-container text-on-surface font-medium" },
  categorical_slicer: { label: "Categorical Slicer", icon: "filter_alt", pill: "bg-surface-container text-on-surface font-medium" },
  flag: { label: "Flag", icon: "flag", pill: "bg-surface-container text-on-surface font-medium" },
  attribute: { label: "Attribute", icon: "label", pill: "bg-surface-container text-on-surface-variant font-medium" },
  identifier: { label: "Identifier", icon: "fingerprint", pill: "bg-surface-container text-on-surface-variant font-medium" },
};

export function roleLabel(col: ColumnProfile): string {
  const base = ROLE_STYLES[col.role].label;
  return col.role === "foreign_key" && col.role_target ? `${base} ↗ ${col.role_target}` : base;
}

function compact(n: number, currency?: string | null, pct = false): string {
  const digits = Number.isInteger(n) ? 0 : 2;
  const s = n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: 2 });
  return `${currency ?? ""}${s}${pct ? "%" : ""}`;
}

/** "Distinct count" cell: ranges for measures, spans for dates, counts otherwise. */
export function distinctSummary(col: ColumnProfile, rows: number): { main: string; note?: string } {
  if (col.numeric && col.role === "measure") {
    const pct = col.detected_type === "percentage";
    return {
      main: `${compact(col.numeric.min, col.currency_symbol, pct)} – ${compact(col.numeric.max, col.currency_symbol, pct)}`,
      note: col.numeric.outliers ? `${formatNumber(col.numeric.outliers)} outliers` : undefined,
    };
  }
  if (col.dates) {
    return { main: `${formatNumber(col.distinct_count)} values`, note: `(${formatNumber(col.dates.span_days)} Days)` };
  }
  if (col.distinct_count === rows && rows > 0) {
    return { main: formatNumber(col.distinct_count), note: "(100% Unique)" };
  }
  const noun = col.role === "geo_dimension" ? " Places" : col.role === "categorical_slicer" ? " Distinct" : "";
  return { main: `${formatNumber(col.distinct_count)}${noun}` };
}

export function confidenceTone(c: number): { label: string; className: string } {
  if (c >= 0.9) return { label: "High", className: "bg-[#E6F4EA] text-[#137333]" };
  if (c >= 0.7) return { label: "Medium", className: "bg-secondary-container/40 text-on-secondary-container" };
  return { label: "Low", className: "bg-error-container text-on-error-container" };
}

export function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
