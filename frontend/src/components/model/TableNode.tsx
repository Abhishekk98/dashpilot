"use client";

import { forwardRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { ModelColumn, TableKind } from "@/lib/api";
import { TYPE_STYLES, formatNumber } from "@/lib/format";

const MAX_COLUMNS = 6;

export interface NodeData {
  name: string;
  kind: TableKind;
  rows: number | null;
  grain: string | null;
  columns: ModelColumn[];
  subtitle?: string;
}

interface TableNodeProps {
  node: NodeData;
  /** Swap fact <-> dimension (not for the date table). */
  onToggleKind?: () => void;
  onExclude?: () => void;
}

function nodeIcon(node: NodeData): string {
  if (node.kind === "date") return "calendar_today";
  if (node.kind === "fact") return "table_chart";
  const n = node.name.toLowerCase();
  if (/customer|client|user|member/.test(n)) return "person";
  if (/product|item|sku/.test(n)) return "inventory_2";
  if (/city|region|geo|location|store|country/.test(n)) return "location_on";
  if (/segment|category|group/.test(n)) return "category";
  return "dataset";
}

function typeLabel(c: ModelColumn): string {
  return c.derived ? "Date key" : (TYPE_STYLES[c.detected_type]?.label ?? c.data_type);
}

function ColumnRow({ c, dark }: { c: ModelColumn; dark: boolean }) {
  const keyRow = c.key !== null;
  const base = dark ? "text-on-primary/90" : "text-on-surface-variant";
  const highlight = c.key === "pk" ? (dark ? "bg-surface-container-highest/10 text-on-primary font-medium" : "bg-secondary-container/20 text-on-surface font-medium") : base;
  return (
    <div className={`flex items-center justify-between gap-2 px-2 py-0.5 rounded ${highlight} ${c.hidden ? "opacity-60" : ""}`}>
      <span className="flex items-center gap-1.5 min-w-0">
        {keyRow ? (
          <Icon name={c.key === "pk" ? "key" : "link"} className={`text-[13px] ${dark ? "text-secondary-container" : "text-secondary"}`} />
        ) : c.measure_candidate ? (
          <Icon name="bar_chart" className={`text-[13px] ${dark ? "text-secondary-container" : "text-on-surface-variant"}`} />
        ) : null}
        <span className="truncate">{c.name}</span>
        {c.hidden && <Icon name="visibility_off" className="text-[12px] shrink-0" />}
      </span>
      <span className={`text-[10px] shrink-0 ${dark ? "text-on-primary-container" : "text-outline-variant"} ${keyRow ? "uppercase" : ""}`}>
        {keyRow ? c.key : typeLabel(c)}
      </span>
    </div>
  );
}

function ColumnList({ columns, dark, title }: { columns: ModelColumn[]; dark: boolean; title?: string }) {
  const [all, setAll] = useState(false);
  const shown = all ? columns : columns.slice(0, MAX_COLUMNS);
  return (
    <div className="space-y-1 min-w-0">
      {title && <div className="text-[10px] uppercase font-semibold text-secondary-container tracking-wider px-2">{title}</div>}
      {shown.map((c) => (
        <ColumnRow key={c.name} c={c} dark={dark} />
      ))}
      {columns.length > MAX_COLUMNS && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className={`px-2 text-[10px] underline underline-offset-2 ${dark ? "text-on-primary-container" : "text-on-surface-variant"}`}
        >
          {all ? "Show less" : `+ ${columns.length - MAX_COLUMNS} more`}
        </button>
      )}
    </div>
  );
}

/** One table card in the star schema diagram (dark hero card for facts). */
export const TableNode = forwardRef<HTMLDivElement, TableNodeProps>(function TableNode({ node, onToggleKind, onExclude }, ref) {
  const fact = node.kind === "fact";
  const keys = node.columns.filter((c) => c.key !== null);
  const rest = node.columns.filter((c) => c.key === null);

  const actions = (onToggleKind || onExclude) && (
    <span className="flex items-center gap-0.5">
      {onToggleKind && (
        <button
          type="button"
          title={fact ? "Make dimension" : "Make fact"}
          aria-label={fact ? `Make ${node.name} a dimension` : `Make ${node.name} a fact`}
          onClick={onToggleKind}
          className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors ${fact ? "text-on-primary-container hover:text-on-primary" : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container"}`}
        >
          <Icon name="swap_horiz" className="text-[15px]" />
        </button>
      )}
      {onExclude && (
        <button
          type="button"
          title="Exclude from model"
          aria-label={`Exclude ${node.name} from the model`}
          onClick={onExclude}
          className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors ${fact ? "text-on-primary-container hover:text-on-primary" : "text-on-surface-variant hover:text-error hover:bg-surface-container"}`}
        >
          <Icon name="block" className="text-[15px]" />
        </button>
      )}
    </span>
  );

  if (fact) {
    const measures = rest.filter((c) => c.measure_candidate);
    const attributes = [...keys, ...rest.filter((c) => !c.measure_candidate)];
    return (
      <div ref={ref} className="w-full max-w-xl rounded-panel bg-primary-container text-on-primary p-5 shadow-[0_20px_48px_-10px_rgba(0,0,0,0.35)] ring-2 ring-secondary-container/40">
        <div className="flex items-center justify-between gap-2 pb-3.5 mb-3 border-b border-surface-container-highest/20">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-surface-container-highest/20 flex items-center justify-center text-secondary-container shrink-0">
              <Icon name="table_chart" className="text-[18px]" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-headline-md text-headline-md tracking-tight text-on-primary font-semibold truncate">{node.name}</span>
                <span className="px-2 py-0.5 rounded-full bg-secondary-container text-primary font-label-sm text-label-sm font-bold shrink-0">FACT</span>
              </div>
              <span className="font-code-sm text-code-sm text-on-primary-container">
                {node.rows !== null && `${formatNumber(node.rows)} rows`}
                {node.grain && ` • Grain: ${node.grain}`}
              </span>
            </div>
          </div>
          {actions}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 font-code-sm text-code-sm">
          <ColumnList columns={attributes} dark title="Keys & Dimensions" />
          <ColumnList columns={measures} dark title="Metrics & Facts" />
        </div>
      </div>
    );
  }

  return (
    <div ref={ref} className="w-full max-w-sm rounded-[20px] bg-surface-container-lowest/90 backdrop-blur-md p-4 shadow-[0_8px_24px_-4px_rgba(35,35,35,0.06)]">
      <div className="flex items-center justify-between gap-2 pb-2.5 mb-2.5 border-b border-surface-container">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded-lg bg-surface-container-high flex items-center justify-center text-on-surface shrink-0">
            <Icon name={nodeIcon(node)} className="text-[15px]" />
          </div>
          <span className="font-title-lg text-title-lg text-on-surface font-semibold tracking-tight truncate">{node.name}</span>
        </div>
        <span className="flex items-center gap-1 shrink-0">
          {node.kind === "date" ? (
            <span className="px-2 py-0.5 rounded-full bg-secondary-container/50 font-label-sm text-label-sm text-on-secondary-fixed-variant font-semibold">★ Date Table</span>
          ) : (
            <span className="px-2 py-0.5 rounded-full bg-surface-container-low font-code-sm text-code-sm text-on-surface-variant">
              {node.rows !== null ? `${formatNumber(node.rows)} rows` : node.subtitle}
            </span>
          )}
          {actions}
        </span>
      </div>
      <div className="font-code-sm text-code-sm">
        <ColumnList columns={[...keys, ...rest]} dark={false} />
      </div>
    </div>
  );
});
