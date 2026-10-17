/** DAX display helpers for the KPIs & DAX studio. */

import type { ReactNode } from "react";

import type { Measure, MeasureFormat } from "./api";

export const FOLDERS = ["01 Base Measures", "02 Ratios & Margins", "03 Time Intelligence", "04 Rankings & Pareto", "05 Custom"];

export const FORMAT_LABELS: Record<MeasureFormat, string> = {
  currency: "Currency",
  whole: "Whole Number",
  decimal: "Decimal",
  percent: "Percentage",
};

export const SOURCE_LABELS: Record<Measure["source"], string> = {
  library: "Industry KPI",
  rules: "Model Rule",
  ai: "AI Suggested",
  user: "Custom",
};

export function measureIcon(m: Measure): string {
  if (m.folder.startsWith("03")) return m.name.endsWith("%") ? "trending_up" : m.name.includes("PY") ? "history" : "calendar_today";
  if (m.format === "percent") return "percent";
  if (m.folder.startsWith("04")) return "leaderboard";
  return "calculate";
}

const TOKEN = /(\/\/[^\n]*|--[^\n]*)|("(?:[^"]|"")*")|('(?:[^']|'')*')|(\[(?:[^\]]|\]\])*\])|([A-Za-z_][A-Za-z0-9_.]*)(?=\s*\()|\b(VAR|RETURN|IN|NOT|AND|OR|ASC|DESC|DAY|MONTH|YEAR)\b|(\d+(?:\.\d+)?)/g;

/** Syntax colouring for the dark inspector code block (design colours). */
export function highlightDax(code: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of code.matchAll(TOKEN)) {
    const [text, comment, str, table, bracket, fn, keyword, num] = m;
    const i = m.index ?? 0;
    if (i > last) out.push(code.slice(last, i));
    const cls = comment
      ? "text-on-primary-container"
      : str
        ? "text-[#A5D6A7]"
        : table
          ? "text-[#90CAF9]"
          : bracket
            ? "text-on-primary font-medium"
            : fn
              ? "text-secondary-container"
              : keyword
                ? "text-on-primary-container font-semibold"
                : num
                  ? "text-[#F6B26B]"
                  : "";
    out.push(
      <span key={i} className={cls}>
        {text}
      </span>,
    );
    last = i + text.length;
  }
  out.push(code.slice(last));
  return out;
}

/** One-line preview of a formula for the list rows. */
export function shortDax(expression: string, max = 70): string {
  const flat = expression.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}
