"use client";

import { TYPE_LABELS } from "@/components/design/visualTypes";
import { Icon } from "@/components/ui/Icon";
import type { DetectedBox, MappingEdit, MappingItem, PlanVisual } from "@/lib/api";

const field = "w-full px-2.5 py-1 rounded-lg bg-surface-container-lowest text-on-surface font-code-sm text-code-sm outline-none focus:ring-2 focus:ring-secondary-container";

function badge(item: MappingItem | undefined, placed: boolean, edited: boolean) {
  if (!placed) return { text: "Unmatched", cls: "bg-error-container text-on-error-container" };
  if (edited || item?.method === "manual") return { text: "Manual", cls: "bg-surface-container text-on-surface" };
  if (item?.method === "id") return { text: "ID match", cls: "bg-secondary-fixed/50 text-on-secondary-fixed" };
  if (item?.method === "title") return { text: `Title ${Math.round((item.score ?? 0) * 100)}% match`, cls: "bg-secondary-fixed/50 text-on-secondary-fixed" };
  if (item?.method === "ai") return { text: "AI match · check", cls: "bg-secondary-container text-on-secondary-fixed" };
  return { text: "Placed", cls: "bg-surface-container text-on-surface" };
}

interface Props {
  visuals: PlanVisual[];
  mapping: MappingEdit[];
  saved: MappingItem[];
  boxes: DetectedBox[];
  selected: string | null;
  problems: Set<string>;
  onSelect: (visualId: string | null) => void;
  onChange: (visualId: string, patch: Partial<MappingEdit>) => void;
}

/** Right-hand "Visual Mapping" list: one card per planned visual with its slot and position. */
export function MappingPanel({ visuals, mapping, saved, boxes, selected, problems, onSelect, onChange }: Props) {
  const byVisual = new Map(mapping.map((m) => [m.visual_id, m]));
  const savedBy = new Map(saved.map((m) => [m.visual_id, m]));
  const owner = new Map(mapping.filter((m) => m.box_id).map((m) => [m.box_id as string, m.visual_id]));
  const titleOf = new Map(visuals.map((v) => [v.id, v.title]));

  return (
    <div className="flex flex-col gap-3">
      {visuals.map((v, i) => {
        const m = byVisual.get(v.id) ?? { visual_id: v.id, box_id: null, x: 0, y: 0, w: 0, h: 0 };
        const s = savedBy.get(v.id);
        const placed = m.w > 0 && m.h > 0;
        const edited = !!s && (s.box_id !== m.box_id || s.x !== m.x || s.y !== m.y || s.w !== m.w || s.h !== m.h);
        const b = badge(s, placed, edited);
        const open = selected === v.id;
        const bad = problems.has(v.id);
        return (
          <div
            key={v.id}
            className={`p-4 rounded-2xl flex flex-col gap-2.5 transition-all ${bad ? "bg-error-container/30 ring-2 ring-error/60" : "bg-surface-container-low hover:bg-surface-container/60"} ${open ? "ring-2 ring-secondary-container" : ""}`}
          >
            <button type="button" onClick={() => onSelect(open ? null : v.id)} className="flex items-start justify-between gap-2 text-left">
              <span className="flex items-start gap-2 min-w-0">
                <span className="w-6 h-6 shrink-0 rounded-full bg-primary-container text-secondary-container font-code-sm text-code-sm flex items-center justify-center font-bold">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="flex flex-col min-w-0">
                  <span className="font-title-lg text-[15px] leading-tight font-medium text-on-surface">{v.title}</span>
                  <span className="font-label-md text-label-md text-on-surface-variant">{TYPE_LABELS[v.type] ?? v.type}</span>
                </span>
              </span>
              <span className={`shrink-0 px-2.5 py-0.5 rounded-full font-code-sm text-code-sm font-semibold ${b.cls}`}>{b.text}</span>
            </button>

            {(v.measures.length > 0 || v.dimension) && (
              <div className="bg-surface-container-lowest p-2.5 rounded-xl font-code-sm text-code-sm text-on-surface-variant break-all">
                {v.measures.map((x, n) => (
                  <span key={x}>
                    {n > 0 && ", "}
                    <span className="text-on-secondary-container font-medium">[{x}]</span>
                  </span>
                ))}
                {v.dimension && (
                  <>
                    {v.measures.length > 0 && " × "}
                    <span className="text-on-surface">{v.dimension}</span>
                  </>
                )}
              </div>
            )}

            <label className="flex items-center justify-between gap-3 pt-0.5">
              <span className="font-label-sm text-label-sm text-on-surface-variant shrink-0">Slot Target</span>
              <select
                value={m.box_id ?? (placed ? "__manual" : "")}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === "") onChange(v.id, { box_id: null, x: 0, y: 0, w: 0, h: 0 });
                  else if (val !== "__manual") {
                    const box = boxes.find((x) => x.id === val);
                    if (box) onChange(v.id, { box_id: box.id, x: box.x, y: box.y, w: box.w, h: box.h });
                  }
                  onSelect(v.id);
                }}
                className="min-w-0 max-w-[230px] px-3 py-1 rounded-full bg-surface-container-lowest text-on-surface font-label-md text-label-md shadow-xs outline-none focus:ring-2 focus:ring-secondary-container"
              >
                <option value="">— Not placed —</option>
                {placed && !m.box_id && <option value="__manual">Placed by hand</option>}
                {boxes.map((box) => {
                  const by = owner.get(box.id);
                  return (
                    <option key={box.id} value={box.id}>
                      {box.id.replace("box_", "#")} · {box.title || "untitled"} ({box.w}×{box.h}){by && by !== v.id ? ` · used by ${titleOf.get(by) ?? by}` : ""}
                    </option>
                  );
                })}
              </select>
            </label>

            {s?.pbi_title && placed && !edited && (
              <p className="flex items-start gap-1.5 font-body-md text-[11px] text-on-surface-variant">
                <Icon name="title" className="text-[14px] shrink-0" /> This slot shows another title in the design, so Power BI will draw &quot;{v.title}&quot; itself.
              </p>
            )}

            {open && (
              <div className="flex flex-col gap-2">
                {placed ? (
                  <div className="grid grid-cols-4 gap-2">
                    {(["x", "y", "w", "h"] as const).map((k) => (
                      <label key={k} className="flex flex-col gap-0.5">
                        <span className="font-label-sm text-[11px] text-on-surface-variant uppercase">{k}</span>
                        <input
                          type="number"
                          className={field}
                          value={m[k]}
                          min={k === "w" ? 40 : k === "h" ? 30 : 0}
                          max={k === "x" || k === "w" ? 1280 : 720}
                          onChange={(e) => onChange(v.id, { [k]: Math.max(0, Math.round(Number(e.target.value) || 0)) })}
                        />
                      </label>
                    ))}
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => onChange(v.id, { box_id: null, x: 24, y: 192, w: v.role === "kpi" ? 233 : v.role === "slicer" ? 176 : 400, h: v.role === "kpi" ? 104 : v.role === "slicer" ? 40 : 244 })}
                    className="self-start px-3 py-1.5 rounded-full bg-surface-container-lowest text-on-surface font-label-md text-label-md flex items-center gap-1.5 shadow-xs hover:bg-surface-container"
                  >
                    <Icon name="add_box" className="text-[16px]" /> Place by hand
                  </button>
                )}
                <p className="font-body-md text-[11px] text-on-surface-variant">
                  Drag the box on the canvas to move it, or the round handle to resize. Click a dashed unused slot to use it for this visual.
                </p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
