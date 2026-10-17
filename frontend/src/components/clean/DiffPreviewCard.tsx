"use client";

import { useState } from "react";

import type { DiffCell, DiffPreview } from "@/lib/api";
import { formatNumber } from "@/lib/format";

/** Side-by-side shows at most this many changed columns as Before/After pairs. */
const MAX_SPLIT_COLUMNS = 2;

const STATUS_PILLS: Record<DiffPreview["rows"][number]["status"], { label: string; className: string }> = {
  transformed: { label: "Transformed", className: "bg-secondary-container/40 text-on-secondary-container" },
  unchanged: { label: "Unchanged", className: "bg-surface-container text-on-surface-variant" },
  duplicate: { label: "Duplicate", className: "bg-error-container text-on-error-container font-medium" },
  removed: { label: "Removed", className: "bg-error-container text-on-error-container font-medium" },
};

function Value({ value }: { value: string | null }) {
  return value === null ? <span className="italic text-outline">null</span> : <>{value}</>;
}

function After({ cell }: { cell: DiffCell }) {
  if (!cell.changed) return <Value value={cell.after} />;
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-secondary-container/40 text-on-surface font-medium">
      <span className="w-1.5 h-1.5 rounded-full bg-secondary-container" />
      <Value value={cell.after} />
    </span>
  );
}

/** "Live Diff Preview": sample rows before and after the accepted steps of one table. */
export function DiffPreviewCard({ preview, loading }: { preview: DiffPreview | null; loading: boolean }) {
  const [mode, setMode] = useState<"split" | "unified">("split");

  const columns = preview?.columns ?? [];
  const key = columns[0];
  const split = new Set(
    mode === "split" ? (preview?.changed_columns ?? []).filter((c) => c !== key && columns.includes(c)).slice(0, MAX_SPLIT_COLUMNS) : [],
  );
  const subtitle = !preview
    ? "Loading sample rows…"
    : preview.accepted_steps === 0
      ? "Accept a suggestion to see its effect on your data"
      : `${formatNumber(preview.transformed_rows)} rows transformed • ${formatNumber(preview.dropped_rows)} dropped • ${preview.accepted_steps} accepted ${preview.accepted_steps === 1 ? "step" : "steps"}`;

  return (
    <div className="p-6 rounded-card bg-surface-container-lowest/80 backdrop-blur-md shadow-card flex flex-col gap-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-title-lg text-title-lg text-on-surface font-medium truncate">
            Live Diff Preview{preview ? `: ${preview.table}` : ""}
          </h2>
          <p className="font-label-sm text-label-sm text-on-surface-variant">{subtitle}</p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <div className="flex items-center p-1 rounded-full bg-surface-container-low">
            {(["split", "unified"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`px-3 py-1 rounded-full font-label-md text-label-md transition-colors ${
                  mode === m ? "bg-surface-container-lowest text-on-surface shadow-xs font-medium" : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {m === "split" ? "Side-by-Side" : "Unified"}
              </button>
            ))}
          </div>
          <span className="font-code-sm text-code-sm text-on-surface-variant px-2.5 py-1 rounded-full bg-surface-container-low">
            {preview?.rows.length ?? 0} rows
          </span>
        </div>
      </div>

      <div className={`w-full overflow-x-auto rounded-2xl bg-surface-container-lowest transition-opacity ${loading ? "opacity-50" : ""}`}>
        <table className="w-full text-left font-code-sm text-code-sm border-collapse min-w-[580px]">
          <thead>
            <tr className="bg-surface-container-low text-on-surface-variant text-[11px] uppercase tracking-wider">
              <th className="py-3 px-3.5 font-medium w-12 text-center">#</th>
              {columns.flatMap((c) =>
                split.has(c)
                  ? [
                      <th key={`${c}-b`} className="py-3 px-3.5 font-medium">{c} (Before)</th>,
                      <th key={`${c}-a`} className="py-3 px-3.5 font-medium">{c} (After)</th>,
                    ]
                  : [<th key={c} className="py-3 px-3.5 font-medium">{c}</th>],
              )}
              <th className="py-3 px-3.5 font-medium text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-container/60">
            {preview?.rows.map((r) => {
              const dropped = r.status === "duplicate" || r.status === "removed";
              const pill = STATUS_PILLS[r.status];
              return (
                <tr
                  key={r.row}
                  className={dropped ? "bg-error-container/20 text-on-surface-variant" : "hover:bg-surface-container-low/40 transition-colors"}
                >
                  <td className={`py-3 px-3.5 text-center ${dropped ? "text-error" : "text-on-surface-variant"}`}>{r.row}</td>
                  {r.cells.flatMap((cell, i) => {
                    const col = columns[i];
                    const isKey = i === 0;
                    const base = `py-3 px-3.5 ${isKey ? "font-medium" : ""}`;
                    if (dropped) {
                      const cls = `${base} line-through ${isKey ? "text-error" : ""}`;
                      return split.has(col)
                        ? [
                            <td key={`${col}-b`} className={cls}><Value value={cell.before} /></td>,
                            <td key={`${col}-a`} className={`${base} text-error italic`}>-- [Dropped] --</td>,
                          ]
                        : [<td key={col} className={cls}><Value value={cell.before} /></td>];
                    }
                    if (split.has(col)) {
                      return [
                        <td key={`${col}-b`} className={`${base} ${cell.changed ? "text-on-surface-variant line-through decoration-outline" : "text-on-surface"}`}>
                          <Value value={cell.before} />
                        </td>,
                        <td key={`${col}-a`} className={`${base} text-on-surface`}><After cell={cell} /></td>,
                      ];
                    }
                    return [
                      <td key={col} className={`${base} text-on-surface`}>
                        {cell.changed ? (
                          <span className="inline-flex flex-wrap items-center gap-1.5">
                            <span className="text-on-surface-variant line-through decoration-outline">
                              <Value value={cell.before} />
                            </span>
                            <After cell={cell} />
                          </span>
                        ) : (
                          <Value value={cell.after} />
                        )}
                      </td>,
                    ];
                  })}
                  <td className="py-3 px-3.5 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] whitespace-nowrap ${pill.className}`}>{pill.label}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-4 pt-1 font-label-md text-label-md text-on-surface-variant">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-secondary-container" />
          <span>Transformed Value</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-surface-container-highest" />
          <span>Unchanged</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-error" />
          <span>Dropped Row</span>
        </div>
      </div>
    </div>
  );
}
