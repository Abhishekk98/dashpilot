"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";

import type { ModelColumn, ModelPlan, Relationship } from "@/lib/api";

import { type NodeData, TableNode } from "./TableNode";

/** Columns of the auto date table, mirrored from backend/core/tmdl.py for the diagram. */
const DATE_COLUMNS: ModelColumn[] = (
  [
    ["Date", "date"],
    ["Year", "integer"],
    ["Quarter", "category"],
    ["Month Name", "category"],
    ["Year Month", "category"],
    ["Week of Year", "integer"],
    ["Day of Week", "category"],
    ["Fiscal Year", "category"],
    ["Fiscal Quarter", "category"],
  ] as const
).map(([name, type]) => ({
  name,
  data_type: type === "date" ? "dateTime" : type === "integer" ? "int64" : "string",
  detected_type: type,
  key: name === "Date" ? "pk" : null,
  hidden: false,
  measure_candidate: false,
  derived: false,
}));

interface Edge {
  rel: Relationship;
  d: string;
  mid: { x: number; y: number };
  down: boolean;
}

interface SchemaDiagramProps {
  plan: ModelPlan;
  zoom: number;
  showFilters: boolean;
  onToggleKind: (table: string, kind: "fact" | "dimension") => void;
  onExclude: (table: string) => void;
}

/** Star schema canvas: dimensions above and below the fact table(s), SVG connectors with cardinality pills. */
export function SchemaDiagram({ plan, zoom, showFilters, onToggleKind, onExclude }: SchemaDiagramProps) {
  const canvas = useRef<HTMLDivElement>(null);
  const nodes = useRef(new Map<string, HTMLDivElement>());
  const [edges, setEdges] = useState<Edge[]>([]);

  const included = plan.tables.filter((t) => t.included);
  const facts: NodeData[] = included.filter((t) => t.kind === "fact");
  const dims: NodeData[] = included.filter((t) => t.kind !== "fact");
  if (plan.date_table.enabled) {
    dims.push({
      name: plan.date_table.name,
      kind: "date",
      rows: null,
      grain: null,
      columns: DATE_COLUMNS,
      subtitle: `${plan.date_table.start?.slice(0, 4)}–${plan.date_table.end?.slice(0, 4)}`,
    });
  }
  const top = dims.slice(0, Math.ceil(dims.length / 2));
  const bottom = dims.slice(Math.ceil(dims.length / 2));

  const measure = useCallback(() => {
    const root = canvas.current;
    if (!root) return;
    const origin = root.getBoundingClientRect();
    // Rects are in zoomed screen pixels; the SVG lives inside the zoomed canvas.
    const box = (name: string) => {
      const el = nodes.current.get(name);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        left: (r.left - origin.left) / zoom,
        top: (r.top - origin.top) / zoom,
        width: r.width / zoom,
        height: r.height / zoom,
      };
    };
    const next: Edge[] = [];
    for (const rel of plan.relationships) {
      const a = box(rel.from_table);
      const b = box(rel.to_table);
      if (!a || !b) continue;
      const ac = { x: a.left + a.width / 2, y: a.top + a.height / 2 };
      const bc = { x: b.left + b.width / 2, y: b.top + b.height / 2 };
      let d: string;
      let mid: { x: number; y: number };
      if (Math.abs(bc.y - ac.y) > 40) {
        // Vertical link: leave from the facing edges.
        const down = bc.y > ac.y;
        const p1 = { x: ac.x, y: down ? a.top + a.height : a.top };
        const p2 = { x: bc.x, y: down ? b.top : b.top + b.height };
        const dy = (p2.y - p1.y) / 2;
        d = `M ${p1.x} ${p1.y} C ${p1.x} ${p1.y + dy}, ${p2.x} ${p2.y - dy}, ${p2.x} ${p2.y}`;
        mid = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
      } else {
        const right = bc.x > ac.x;
        const p1 = { x: right ? a.left + a.width : a.left, y: ac.y };
        const p2 = { x: right ? b.left : b.left + b.width, y: bc.y };
        const dx = (p2.x - p1.x) / 2;
        d = `M ${p1.x} ${p1.y} C ${p1.x + dx} ${p1.y}, ${p2.x - dx} ${p2.y}, ${p2.x} ${p2.y}`;
        mid = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
      }
      // The "1" side is to_table; the pill arrow points from the one side to the many side.
      next.push({ rel, d, mid, down: bc.y < ac.y });
    }
    setEdges(next);
  }, [plan, zoom]);

  useLayoutEffect(() => {
    measure();
    const root = canvas.current;
    if (!root) return;
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    return () => observer.disconnect();
  }, [measure]);

  const setRef = (name: string) => (el: HTMLDivElement | null) => {
    if (el) nodes.current.set(name, el);
    else nodes.current.delete(name);
  };

  const node = (n: NodeData) => (
    <TableNode
      key={n.name}
      ref={setRef(n.name)}
      node={n}
      onToggleKind={n.kind === "date" ? undefined : () => onToggleKind(n.name, n.kind === "fact" ? "dimension" : "fact")}
      onExclude={n.kind === "date" ? undefined : () => onExclude(n.name)}
    />
  );

  return (
    <div ref={canvas} style={{ zoom }} className="relative w-full flex flex-col gap-12 py-2">
      <svg className="absolute inset-0 w-full h-full pointer-events-none overflow-visible" aria-hidden="true">
        <defs>
          <linearGradient id="relGlow" x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="#C4C7C7" stopOpacity="0.7" />
            <stop offset="50%" stopColor="#F8CF4B" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#C4C7C7" stopOpacity="0.7" />
          </linearGradient>
        </defs>
        {edges.map(({ rel, d }) => (
          <path
            key={rel.id}
            d={d}
            fill="none"
            stroke={!rel.valid ? "#BA1A1A" : rel.active ? "url(#relGlow)" : "#C4C7C7"}
            strokeWidth={2}
            strokeDasharray={rel.active && rel.valid ? undefined : "5 5"}
          />
        ))}
      </svg>

      {top.length > 0 && <div className="relative grid grid-cols-1 sm:grid-cols-2 gap-6 lg:gap-12 justify-items-center">{top.map(node)}</div>}
      <div className="relative flex flex-wrap justify-center gap-8">
        {facts.length ? (
          facts.map(node)
        ) : (
          <div className="px-6 py-10 rounded-panel bg-surface-container-low/80 text-on-surface-variant font-body-md text-body-md">
            No fact table yet: use the swap button on a table to make it the fact.
          </div>
        )}
      </div>
      {bottom.length > 0 && <div className="relative grid grid-cols-1 sm:grid-cols-2 gap-6 lg:gap-12 justify-items-center">{bottom.map(node)}</div>}

      {edges.map(({ rel, mid, down }) => (
        <span
          key={rel.id}
          title={rel.note ?? `${rel.from_table}.${rel.from_column} → ${rel.to_table}.${rel.to_column}`}
          style={{ left: mid.x, top: mid.y }}
          className={`absolute -translate-x-1/2 -translate-y-1/2 z-10 px-2.5 py-0.5 rounded-full shadow-md font-code-sm text-code-sm flex items-center gap-1 border ${
            !rel.valid
              ? "bg-error-container text-on-error-container border-error/40"
              : rel.active
                ? "bg-surface-container-lowest text-on-surface border-secondary-container/50"
                : "bg-surface-container-low text-on-surface-variant border-outline-variant/40"
          }`}
        >
          <span className="font-bold text-secondary">1</span>
          <span className="material-symbols-outlined text-[12px] text-secondary" aria-hidden="true">
            {down ? "arrow_downward" : "arrow_upward"}
          </span>
          <span className="font-bold">{rel.cardinality === "one_to_one" ? "1" : "*"}</span>
          {showFilters && <span className="ml-1 text-[10px] text-on-surface-variant">{rel.cross_filter === "both" ? "⇄" : "→"}</span>}
          {!rel.active && rel.valid && <span className="ml-1 text-[10px] text-on-surface-variant">inactive</span>}
        </span>
      ))}
    </div>
  );
}
