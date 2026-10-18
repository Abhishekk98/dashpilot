"use client";

import { Icon } from "@/components/ui/Icon";
import type { DashboardPlan, VisualInput } from "@/lib/api";

import { MULTI_MEASURE, TYPE_ICONS, TYPE_LABELS } from "./visualTypes";

export interface Draft extends VisualInput {
  /** Stable React key; the server re-numbers ids on save. */
  key: string;
}

const ROLE_LABELS: Record<VisualInput["role"], string> = { slicer: "Slicer", kpi: "KPI card", chart: "Chart", insights: "Key Insights" };

const field = "w-full px-3 py-1.5 rounded-xl bg-surface-container-low text-on-surface font-body-md text-xs outline-none focus:ring-2 focus:ring-secondary-container";

interface Props {
  plan: DashboardPlan;
  drafts: Draft[];
  selected: string | null;
  onSelect: (key: string) => void;
  onChange: (drafts: Draft[]) => void;
}

/** Ordered list of the plan's visuals with type/field/measure editing, reorder and remove. */
export function VisualEditor({ plan, drafts, selected, onSelect, onChange }: Props) {
  const update = (key: string, patch: Partial<Draft>) => onChange(drafts.map((d) => (d.key === key ? { ...d, ...patch } : d)));
  const move = (index: number, delta: number) => {
    const target = index + delta;
    // Only reorder within the same role; the layout groups slicers, KPIs and charts.
    if (target < 0 || target >= drafts.length || drafts[target].role !== drafts[index].role) return;
    const next = [...drafts];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };
  const dims = plan.dimensions;
  const labelOf = (fieldName: string | null) => dims.find((d) => d.field === fieldName)?.label ?? fieldName ?? "";

  return (
    <ol className="flex flex-col gap-2.5">
      {drafts.map((d, i) => {
        const open = selected === d.key;
        const sameRoleBefore = i > 0 && drafts[i - 1].role === d.role;
        const sameRoleAfter = i < drafts.length - 1 && drafts[i + 1].role === d.role;
        return (
          <li key={d.key} className={`rounded-2xl bg-surface-container-lowest/90 shadow-card ${open ? "ring-2 ring-secondary-container" : ""}`}>
            <div className="flex items-center gap-2 px-3 py-2.5">
              <button type="button" onClick={() => onSelect(open ? "" : d.key)} className="flex items-center gap-2.5 min-w-0 flex-1 text-left">
                <span className="w-8 h-8 shrink-0 rounded-full bg-secondary-container/40 flex items-center justify-center">
                  <Icon name={TYPE_ICONS[d.type] ?? "widgets"} className="text-[18px] text-on-surface" />
                </span>
                <span className="min-w-0 flex flex-col">
                  <span className="font-label-md text-label-md text-on-surface truncate">{d.title || "Untitled"}</span>
                  <span className="font-code-sm text-[11px] text-on-surface-variant truncate">
                    {ROLE_LABELS[d.role]}
                    {d.role === "chart" ? ` · ${TYPE_LABELS[d.type] ?? d.type}` : ""}
                    {d.dimension ? ` · ${d.role === "slicer" ? "on" : "by"} ${labelOf(d.dimension)}` : ""}
                  </span>
                </span>
              </button>
              <div className="flex items-center shrink-0">
                <button type="button" aria-label="Move up" disabled={!sameRoleBefore} onClick={() => move(i, -1)} className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:text-on-surface disabled:opacity-30">
                  <Icon name="arrow_upward" className="text-[16px]" />
                </button>
                <button type="button" aria-label="Move down" disabled={!sameRoleAfter} onClick={() => move(i, 1)} className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:text-on-surface disabled:opacity-30">
                  <Icon name="arrow_downward" className="text-[16px]" />
                </button>
                {d.role !== "insights" && (
                  <button type="button" aria-label={`Remove ${d.title}`} onClick={() => onChange(drafts.filter((x) => x.key !== d.key))} className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:text-error">
                    <Icon name="delete" className="text-[16px]" />
                  </button>
                )}
              </div>
            </div>

            {open && (
              <div className="px-4 pb-4 pt-1 grid grid-cols-2 gap-2.5">
                {d.role !== "kpi" && d.role !== "insights" && (
                  <label className="col-span-2 flex flex-col gap-1">
                    <span className="font-label-sm text-[11px] text-on-surface-variant">Title</span>
                    <input className={field} maxLength={80} value={d.title} onChange={(e) => update(d.key, { title: e.target.value })} />
                  </label>
                )}

                {d.role === "chart" && (
                  <label className="flex flex-col gap-1">
                    <span className="font-label-sm text-[11px] text-on-surface-variant">Chart type</span>
                    <select className={field} value={d.type} onChange={(e) => update(d.key, { type: e.target.value, measures: MULTI_MEASURE.has(e.target.value) ? d.measures : d.measures.slice(0, 1) })}>
                      {plan.chart_types.map((t) => (
                        <option key={t} value={t}>{TYPE_LABELS[t] ?? t}</option>
                      ))}
                    </select>
                  </label>
                )}

                {(d.role === "chart" || d.role === "kpi") && (
                  <label className={`flex flex-col gap-1 ${d.role === "kpi" ? "col-span-2" : ""}`}>
                    <span className="font-label-sm text-[11px] text-on-surface-variant">Measure</span>
                    <select
                      className={field}
                      value={d.measures[0] ?? ""}
                      onChange={(e) => {
                        const measures = [e.target.value, ...d.measures.slice(1).filter((m) => m !== e.target.value)];
                        update(d.key, d.role === "kpi" ? { measures, title: e.target.value } : { measures });
                      }}
                    >
                      {!d.measures[0] && <option value="">Choose a measure</option>}
                      {d.measures[0] && !plan.measures.includes(d.measures[0]) && <option value={d.measures[0]}>{d.measures[0]} (not validated)</option>}
                      {plan.measures.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </label>
                )}

                {d.role === "chart" && MULTI_MEASURE.has(d.type) && (
                  <label className="col-span-2 flex flex-col gap-1">
                    <span className="font-label-sm text-[11px] text-on-surface-variant">Extra measures (optional)</span>
                    <div className="flex flex-wrap gap-1.5">
                      {plan.measures.filter((m) => m !== d.measures[0]).slice(0, 12).map((m) => {
                        const on = d.measures.includes(m);
                        return (
                          <button
                            key={m}
                            type="button"
                            disabled={!on && d.measures.length >= 4}
                            onClick={() => update(d.key, { measures: on ? d.measures.filter((x) => x !== m) : [...d.measures, m] })}
                            className={`px-2.5 py-1 rounded-full font-label-sm text-[11px] disabled:opacity-40 ${on ? "bg-primary-container text-on-primary" : "bg-surface-container-low text-on-surface-variant hover:text-on-surface"}`}
                          >
                            {m}
                          </button>
                        );
                      })}
                    </div>
                  </label>
                )}

                {(d.role === "chart" || d.role === "slicer") && d.type !== "gauge" && (
                  <label className="flex flex-col gap-1">
                    <span className="font-label-sm text-[11px] text-on-surface-variant">{d.role === "slicer" ? "Field" : "Axis / category"}</span>
                    <select className={field} value={d.dimension ?? ""} onChange={(e) => update(d.key, { dimension: e.target.value || null, sort: d.role === "chart" ? (e.target.value.startsWith("Dim_Date[") ? "date" : "desc") : null })}>
                      <option value="">Choose a field</option>
                      {dims.map((o) => (
                        <option key={o.field} value={o.field}>
                          {o.label} ({o.kind === "date" ? "date" : `${o.cardinality} values`})
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                {d.role === "chart" && d.type !== "gauge" && (
                  <label className="flex flex-col gap-1">
                    <span className="font-label-sm text-[11px] text-on-surface-variant">Sort</span>
                    <select className={field} value={d.sort ?? ""} onChange={(e) => update(d.key, { sort: (e.target.value || null) as Draft["sort"] })}>
                      <option value="">Default</option>
                      <option value="desc">Highest first</option>
                      <option value="asc">Lowest first</option>
                      <option value="date">By date</option>
                    </select>
                  </label>
                )}

                {d.purpose && (
                  <p className="col-span-2 flex items-start gap-1.5 font-body-md text-xs text-on-surface-variant">
                    <Icon name="help" className="text-[14px] shrink-0 mt-0.5" /> {d.purpose}
                  </p>
                )}
                {d.role === "insights" && (
                  <ul className="col-span-2 list-disc pl-5 font-body-md text-xs text-on-surface">
                    {d.text.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                    {d.text.length === 0 && <li>Pin insights in Step 6 to show them here.</li>}
                  </ul>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
