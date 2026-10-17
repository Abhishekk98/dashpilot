"use client";

import { useMemo, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { SemanticRole, TableProfile } from "@/lib/api";
import {
  ROLE_STYLES,
  TYPE_STYLES,
  confidenceTone,
  distinctSummary,
  formatNumber,
  roleLabel,
  typeLabel,
} from "@/lib/format";

const PREVIEW_ROWS = 6;

interface ColumnProfileTableProps {
  tables: TableProfile[];
  csvUrl: string;
}

/** "Comprehensive Column Profile Table" with table tabs, search and a role filter. */
export function ColumnProfileTable({ tables, csvUrl }: ColumnProfileTableProps) {
  const [activeName, setActiveName] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<SemanticRole | "all">("all");
  const [showAll, setShowAll] = useState(false);

  // Fall back to the first table if the active one was removed.
  const active = tables.find((t) => t.name === activeName) ?? tables[0];

  const columns = useMemo(() => {
    if (!active) return [];
    const q = query.trim().toLowerCase();
    return active.column_profiles.filter(
      (c) => (role === "all" || c.role === role) && (!q || c.name.toLowerCase().includes(q)),
    );
  }, [active, query, role]);

  if (!active) return null;
  const visible = showAll ? columns : columns.slice(0, PREVIEW_ROWS);
  const rolesInTable = Array.from(new Set(active.column_profiles.map((c) => c.role)));

  return (
    <section className="rounded-card bg-surface-container-lowest/80 backdrop-blur-xl p-7 shadow-card mb-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6">
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {tables.map((t) => {
            const isActive = t.name === active.name;
            return (
              <button
                key={t.name}
                type="button"
                onClick={() => {
                  setActiveName(t.name);
                  setShowAll(false);
                }}
                className={`px-4 py-2 rounded-full font-body-md text-body-md font-medium flex items-center gap-2 shrink-0 transition-colors ${
                  isActive
                    ? "bg-primary-container text-on-primary tracking-tight shadow-sm"
                    : "bg-surface-container hover:bg-surface-container-high text-on-surface-variant"
                }`}
              >
                <span>{t.name}</span>
                <span
                  className={`px-2 py-0.5 rounded-full font-code-sm text-code-sm ${
                    isActive ? "bg-white/20 font-medium" : "bg-surface-container-highest"
                  }`}
                >
                  {t.columns} cols
                </span>
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <Icon name="search" className="absolute left-3.5 top-1/2 -translate-y-1/2 text-on-surface-variant text-[18px]" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search columns..."
              type="text"
              className="pl-10 pr-4 py-2 rounded-full bg-surface-container-low text-on-surface placeholder:text-on-surface-variant font-body-md text-body-md focus:outline-none focus:ring-2 focus:ring-secondary-container transition-all w-52 md:w-64"
            />
          </div>
          <label className="relative h-9 pl-3.5 pr-3 rounded-full bg-surface-container-low hover:bg-surface-container text-on-surface-variant font-body-md text-body-md font-medium flex items-center gap-1.5 transition-colors cursor-pointer">
            <Icon name="filter_list" className="text-[18px]" />
            <span>{role === "all" ? "Role Filter" : ROLE_STYLES[role].label}</span>
            <select
              aria-label="Filter by role"
              value={role}
              onChange={(e) => setRole(e.target.value as SemanticRole | "all")}
              className="absolute inset-0 opacity-0 cursor-pointer"
            >
              <option value="all">All roles</option>
              {rolesInTable.map((r) => (
                <option key={r} value={r}>
                  {ROLE_STYLES[r].label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="w-full overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[900px]">
          <thead>
            <tr className="font-label-sm text-label-sm text-on-surface-variant tracking-wider uppercase">
              <th className="py-3 px-4 font-semibold">Column Name</th>
              <th className="py-3 px-4 font-semibold">Detected Type</th>
              <th className="py-3 px-4 font-semibold w-40">Missing / Null %</th>
              <th className="py-3 px-4 font-semibold">Distinct Count</th>
              <th className="py-3 px-4 font-semibold">AI Semantic Role</th>
              <th className="py-3 px-4 font-semibold">Sample Values</th>
              <th className="py-3 px-4 font-semibold text-right">Confidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-container/60">
            {visible.map((col) => {
              const type = TYPE_STYLES[col.detected_type];
              const roleStyle = ROLE_STYLES[col.role];
              const distinct = distinctSummary(col, active.rows);
              const conf = confidenceTone(col.confidence);
              const filled = 100 - col.null_pct;
              return (
                <tr key={col.name} className="hover:bg-surface-container-low/50 transition-colors">
                  <td className="py-4 px-4">
                    <div className="flex items-center gap-2.5">
                      <Icon name={type.icon} className="text-[18px] text-on-surface-variant" />
                      <span className="font-body-md text-body-md font-semibold text-on-surface">{col.name}</span>
                    </div>
                  </td>
                  <td className="py-4 px-4">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-code-sm text-code-sm font-medium ${type.pill}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${type.dot}`} />
                      {typeLabel(col)}
                    </span>
                  </td>
                  <td className="py-4 px-4">
                    <div className="flex flex-col gap-1">
                      <div className="flex justify-between items-center font-code-sm text-code-sm text-on-surface">
                        <span className={col.null_pct > 0 ? "text-on-secondary-container font-medium" : ""}>
                          {col.null_pct.toFixed(1)}%
                        </span>
                        <span className="text-on-surface-variant text-[10px]">{formatNumber(col.null_count)} rows</span>
                      </div>
                      {/* Filled share in charcoal, missing share hatched in sunflower. */}
                      <div className="w-full h-1.5 rounded-full bg-surface-container overflow-hidden flex">
                        <div className="h-full bg-primary-container" style={{ width: `${filled}%` }} />
                        {col.null_pct > 0 && (
                          <div
                            className="h-full"
                            style={{
                              width: `${col.null_pct}%`,
                              background:
                                "repeating-linear-gradient(45deg, #F8CF4B, #F8CF4B 4px, #FCE89F 4px, #FCE89F 8px)",
                            }}
                          />
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-4 font-code-sm text-code-sm text-on-surface">
                    {distinct.main} {distinct.note && <span className="text-on-surface-variant text-[11px]">{distinct.note}</span>}
                  </td>
                  <td className="py-4 px-4">
                    <span
                      title={col.role_source === "ai" ? "Refined by AI" : "Rule-based detection"}
                      className={`inline-flex items-center gap-1 px-3 py-1 rounded-full font-label-sm text-label-sm whitespace-nowrap ${roleStyle.pill}`}
                    >
                      <Icon name={roleStyle.icon} className={`text-[13px] ${roleStyle.iconClass ?? ""}`} />
                      {roleLabel(col)}
                    </span>
                  </td>
                  <td className="py-4 px-4 font-code-sm text-code-sm text-on-surface-variant max-w-[220px] truncate">
                    {col.sample_values.join(", ")}
                    {col.distinct_count > col.sample_values.length && "..."}
                  </td>
                  <td className="py-4 px-4 text-right">
                    <span className={`px-2.5 py-1 rounded-full font-code-sm text-code-sm font-semibold whitespace-nowrap ${conf.className}`}>
                      {Math.round(col.confidence * 100)}% {conf.label}
                    </span>
                  </td>
                </tr>
              );
            })}
            {visible.length === 0 && (
              <tr>
                <td colSpan={7} className="py-8 text-center font-body-md text-body-md text-on-surface-variant">
                  No columns match your filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-5 mt-2 border-t border-surface-container/60">
        <span className="font-code-sm text-code-sm text-on-surface-variant">
          Displaying {visible.length} of {active.columns} profiled columns • {formatNumber(active.rows)} rows
          {active.sheet && ` • Sheet "${active.sheet}"`}
        </span>
        <div className="flex items-center gap-2">
          {columns.length > PREVIEW_ROWS && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="px-3 py-1 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm transition-colors"
            >
              {showAll ? "Show Fewer Columns" : `Show All ${columns.length} Columns`}
            </button>
          )}
          <a
            href={csvUrl}
            className="px-3 py-1 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm transition-colors"
          >
            Export Profiler CSV
          </a>
        </div>
      </div>
    </section>
  );
}
