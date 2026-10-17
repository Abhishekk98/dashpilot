"use client";

import { useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { ModelPlan, RelationshipInput } from "@/lib/api";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

const NOTE_ICONS = {
  success: { icon: "check_circle", className: "text-pine", box: "bg-surface-container-low/50" },
  info: { icon: "lightbulb", className: "text-secondary", box: "bg-surface-container-low/50" },
  warning: { icon: "warning", className: "text-coral", box: "bg-error-container/30" },
} as const;

interface ModelSidePanelProps {
  plan: ModelPlan;
  busy: boolean;
  onFiscalMonth: (month: number) => void;
  onDateTable: (enabled: boolean) => void;
  onAddRelationship: (rel: RelationshipInput) => void;
  onRemoveRelationship: (id: string) => void;
  onValidate: () => void;
}

function Stat({ value, label, note, tone = "text-on-surface" }: { value: number; label: string; note: string; tone?: string }) {
  return (
    <div className="flex flex-col p-3 rounded-2xl bg-surface-container-low/60 min-w-0">
      <span className={`font-metric-huge text-metric-huge font-light leading-none tracking-tight ${tone}`}>{value}</span>
      <span className="font-label-md text-label-md text-on-surface-variant mt-1">{label}</span>
      <span className="font-code-sm text-code-sm text-outline font-normal truncate">{note}</span>
    </div>
  );
}

/** Right column: model summary, date table settings, AI notes and the relationship list. */
export function ModelSidePanel({ plan, busy, onFiscalMonth, onDateTable, onAddRelationship, onRemoveRelationship, onValidate }: ModelSidePanelProps) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<RelationshipInput>({ from_table: "", from_column: "", to_table: "", to_column: "" });

  const included = plan.tables.filter((t) => t.included);
  const columnsOf = (table: string) => included.find((t) => t.name === table)?.columns.map((c) => c.name) ?? [];
  const valid = plan.relationships.filter((r) => r.valid);
  const oneToMany = valid.length ? Math.round((valid.filter((r) => r.cardinality === "many_to_one").length / valid.length) * 100) : 0;
  const ready = draft.from_table && draft.from_column && draft.to_table && draft.to_column && draft.from_table !== draft.to_table;

  const select = (value: string, onChange: (v: string) => void, options: string[], placeholder: string) => (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 rounded-full bg-surface-container-lowest font-code-sm text-code-sm text-on-surface shadow-sm outline-none focus-halo"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-card bg-surface-container-lowest/80 backdrop-blur-[16px] shadow-card p-6">
        <div className="flex items-center justify-between pb-3 mb-4 border-b border-surface-container">
          <div className="flex items-center gap-2">
            <Icon name="architecture" className="text-on-surface text-[20px]" />
            <span className="font-headline-md text-headline-md tracking-tight text-on-surface font-semibold">Model Summary</span>
          </div>
          <span
            title={plan.tmdl_errors.join("\n") || undefined}
            className={`px-2.5 py-1 rounded-full font-label-sm text-label-sm ${plan.tmdl_valid ? "bg-surface-container-low text-on-surface-variant" : "bg-error-container text-on-error-container"}`}
          >
            {plan.tmdl_valid ? "TMDL Valid" : `TMDL: ${plan.tmdl_errors.length} issue${plan.tmdl_errors.length === 1 ? "" : "s"}`}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-4 pb-5 border-b border-surface-container">
          <Stat value={plan.facts + plan.dimensions} label="Tables Total" note={`${plan.facts} Fact • ${plan.dimensions} Dimensions`} />
          <Stat value={valid.length} label="Relationships" note={`${oneToMany}% 1:Many (1:*)`} tone="text-secondary" />
          <Stat
            value={plan.date_table.enabled ? 1 : 0}
            label="Auto Date Table"
            note={plan.date_table.enabled ? `${plan.date_table.start?.slice(0, 4)}–${plan.date_table.end?.slice(0, 4)}` : "Off"}
          />
          <Stat value={plan.ambiguities} label="Ambiguities" note="Single-direction filters" tone={plan.ambiguities ? "text-coral" : "text-pine"} />
        </div>
        <div className="mt-4 p-3.5 rounded-2xl bg-primary-container text-on-primary flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary-container shrink-0">
              <Icon name="calendar_month" className="text-[18px]" />
            </div>
            <div className="flex flex-col min-w-0">
              <span className="font-label-sm text-label-sm text-secondary-container font-semibold uppercase tracking-wider">Date Intelligence</span>
              <label className="font-code-sm text-code-sm text-on-primary-container flex items-center gap-1.5">
                Fiscal year starts
                <select
                  aria-label="Fiscal year start month"
                  value={plan.settings.fiscal_year_start_month}
                  disabled={busy}
                  onChange={(e) => onFiscalMonth(Number(e.target.value))}
                  className="bg-transparent text-on-primary font-semibold outline-none cursor-pointer"
                >
                  {MONTHS.map((m, i) => (
                    <option key={m} value={i + 1} className="text-on-surface">
                      {m}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={plan.settings.date_table}
            aria-label="Auto date table"
            disabled={busy}
            onClick={() => onDateTable(!plan.settings.date_table)}
            className={`w-10 h-5 rounded-full p-0.5 flex items-center shrink-0 transition-colors ${plan.settings.date_table ? "bg-secondary-container justify-end" : "bg-surface-container-highest/30 justify-start"}`}
          >
            <span className="w-4 h-4 rounded-full bg-primary-container shadow-sm block" />
          </button>
        </div>
      </div>

      <div className="rounded-card bg-surface-container-lowest/80 backdrop-blur-[16px] shadow-card p-6">
        <div className="flex items-center justify-between pb-3 mb-4 border-b border-surface-container">
          <div className="flex items-center gap-2">
            <Icon name="auto_fix_high" className="text-secondary text-[20px]" />
            <span className="font-headline-md text-headline-md tracking-tight text-on-surface font-semibold">AI Synthesizer Notes</span>
          </div>
          <span className={`w-2 h-2 rounded-full bg-secondary-container ${plan.ai_status === "pending" ? "animate-ping" : ""}`} />
        </div>
        <div className="space-y-3">
          {plan.notes.map((n, i) => {
            const style = NOTE_ICONS[n.tone];
            return (
              <div key={`${n.title}-${i}`} className={`flex items-start gap-3 p-2.5 rounded-xl ${style.box}`}>
                <Icon name={style.icon} className={`text-[18px] shrink-0 mt-0.5 ${style.className}`} />
                <p className="text-xs leading-relaxed text-on-surface">
                  <span className="font-semibold">{n.title}:</span> {n.text}
                </p>
              </div>
            );
          })}
          {plan.ai_status === "failed" && plan.ai_note && (
            <p className="px-1 text-xs text-on-surface-variant">AI review skipped: {plan.ai_note}. Showing rule-based model.</p>
          )}
        </div>
      </div>

      <div className="rounded-card bg-surface-container-lowest/80 backdrop-blur-[16px] shadow-card p-5 flex flex-col gap-3">
        <span className="font-title-lg text-title-lg text-on-surface font-semibold px-1">Relationships</span>
        {plan.relationships.length === 0 && <p className="px-1 text-xs text-on-surface-variant">No relationships yet.</p>}
        {plan.relationships.map((r) => (
          <div key={r.id} className={`flex items-center justify-between gap-2 p-2.5 rounded-xl ${r.valid ? "bg-surface-container-low/60" : "bg-error-container/30"}`}>
            <div className="min-w-0 font-code-sm text-code-sm">
              <div className="truncate text-on-surface" title={`${r.from_table}.${r.from_column}`}>
                {r.from_table}.{r.from_column}
              </div>
              <div className="truncate text-on-surface-variant" title={`${r.to_table}.${r.to_column}`}>
                → {r.to_table}.{r.to_column}
              </div>
              <div className="text-[10px] text-outline">
                {r.valid ? (r.cardinality === "one_to_one" ? "1:1" : "*:1") : "invalid"} • {r.active ? "active" : "inactive"} • {r.origin}
              </div>
            </div>
            <button
              type="button"
              aria-label={`Remove relationship ${r.id}`}
              title="Remove relationship"
              disabled={busy}
              onClick={() => onRemoveRelationship(r.id)}
              className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:text-error hover:bg-surface-container shrink-0"
            >
              <Icon name="close" className="text-[16px]" />
            </button>
          </div>
        ))}

        {adding && (
          <div className="flex flex-col gap-2 p-3 rounded-2xl bg-surface-container-low/60">
            <span className="font-label-sm text-label-sm text-on-surface-variant">Many side (e.g. fact)</span>
            {select(draft.from_table, (v) => setDraft({ ...draft, from_table: v, from_column: "" }), included.map((t) => t.name), "Table…")}
            {select(draft.from_column, (v) => setDraft({ ...draft, from_column: v }), columnsOf(draft.from_table), "Column…")}
            <span className="font-label-sm text-label-sm text-on-surface-variant pt-1">One side (unique key)</span>
            {select(draft.to_table, (v) => setDraft({ ...draft, to_table: v, to_column: "" }), included.map((t) => t.name), "Table…")}
            {select(draft.to_column, (v) => setDraft({ ...draft, to_column: v }), columnsOf(draft.to_table), "Column…")}
            <button
              type="button"
              disabled={!ready || busy}
              onClick={() => {
                onAddRelationship(draft);
                setAdding(false);
                setDraft({ from_table: "", from_column: "", to_table: "", to_column: "" });
              }}
              className="mt-1 py-2 rounded-full bg-primary-container text-on-primary font-label-md text-label-md disabled:opacity-50"
            >
              Create relationship
            </button>
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-center gap-3 pt-1">
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            className="w-full sm:flex-1 py-2.5 px-4 rounded-full bg-surface-container text-on-surface font-label-md text-label-md font-semibold hover:bg-surface-container-high transition-all flex items-center justify-center gap-2"
          >
            <Icon name={adding ? "close" : "add_link"} className="text-[17px]" />
            <span>{adding ? "Cancel" : "+ Add Relationship"}</span>
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onValidate}
            className="w-full sm:flex-1 py-2.5 px-4 rounded-full bg-surface-container-low text-on-surface-variant font-label-md text-label-md font-semibold hover:text-on-surface hover:bg-surface-container transition-all flex items-center justify-center gap-2"
          >
            <Icon name="check_box" className="text-[17px]" />
            <span>Validate Cardinality</span>
          </button>
        </div>
      </div>
    </div>
  );
}
