"use client";

import { useRef } from "react";

import { DesignFrame, ScaledCanvas } from "@/components/design/ScaledCanvas";
import type { DetectedBox, MappingEdit, PlanVisual } from "@/lib/api";

const W = 1280;
const H = 720;

interface Props {
  view: "background" | "original";
  backgroundUrl: string;
  /** The design rendered as-is (newer imports); Stitch pages need their scripts, which an iframe preview cannot run. */
  originalUrl?: string | null;
  html: string;
  visuals: PlanVisual[];
  mapping: MappingEdit[];
  boxes: DetectedBox[];
  showBoxes: boolean;
  selected: string | null;
  problems: Set<string>;
  onSelect: (visualId: string) => void;
  onAssignBox: (boxId: string) => void;
  onMove: (visualId: string, patch: Partial<MappingEdit>) => void;
}

/** The 1280x720 design with numbered mapping boxes; boxes can be dragged and resized,
 *  and free detected slots can be clicked to assign them to the selected visual. */
export function MappingCanvas({ view, backgroundUrl, originalUrl, html, visuals, mapping, boxes, showBoxes, selected, problems, onSelect, onAssignBox, onMove }: Props) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const used = new Set(mapping.map((m) => m.box_id).filter(Boolean));
  const titles = new Map(visuals.map((v, i) => [v.id, { n: String(i + 1).padStart(2, "0"), title: v.title }]));

  const drag = (e: React.PointerEvent, m: MappingEdit, mode: "move" | "resize") => {
    e.preventDefault();
    e.stopPropagation();
    onSelect(m.visual_id);
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const scale = rect.width / W;
    const start = { px: e.clientX, py: e.clientY, x: m.x, y: m.y, w: m.w, h: m.h };
    const target = e.currentTarget as HTMLElement;
    target.setPointerCapture(e.pointerId);
    const onMoveEvent = (ev: PointerEvent) => {
      const dx = Math.round((ev.clientX - start.px) / scale);
      const dy = Math.round((ev.clientY - start.py) / scale);
      if (mode === "move") {
        onMove(m.visual_id, { x: Math.min(Math.max(0, start.x + dx), W - start.w), y: Math.min(Math.max(0, start.y + dy), H - start.h) });
      } else {
        onMove(m.visual_id, { w: Math.min(Math.max(40, start.w + dx), W - start.x), h: Math.min(Math.max(30, start.h + dy), H - start.y) });
      }
    };
    const onUp = () => {
      target.removeEventListener("pointermove", onMoveEvent);
      target.removeEventListener("pointerup", onUp);
    };
    target.addEventListener("pointermove", onMoveEvent);
    target.addEventListener("pointerup", onUp);
  };

  return (
    <ScaledCanvas className="rounded-2xl shadow-inner bg-surface-container-low">
      <div ref={canvasRef} className="relative w-[1280px] h-[720px] select-none">
        {view === "original" && originalUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- generated per project, versioned URL
          <img src={originalUrl} alt="Original design" width={W} height={H} className="absolute inset-0 w-full h-full" draggable={false} />
        ) : view === "background" ? (
          // eslint-disable-next-line @next/next/no-img-element -- generated per project, versioned URL
          <img src={backgroundUrl} alt="Clean design background" width={W} height={H} className="absolute inset-0 w-full h-full" draggable={false} />
        ) : (
          <DesignFrame html={html} title="Original design" />
        )}

        {showBoxes &&
          boxes
            .filter((b) => !used.has(b.id))
            .map((b) => (
              <button
                key={b.id}
                type="button"
                title={selected ? `Use this slot for the selected visual (${b.title || b.id})` : b.title || b.id}
                onClick={() => selected && onAssignBox(b.id)}
                className={`absolute rounded-[14px] border-2 border-dashed border-outline/60 bg-surface-container/10 ${selected ? "hover:bg-secondary-container/20 cursor-copy" : "cursor-default"}`}
                style={{ left: b.x, top: b.y, width: b.w, height: b.h }}
              >
                <span className="absolute -top-3 left-3 px-2.5 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-code-sm text-[13px]">
                  Slot {b.id.replace("box_", "#")} · unused
                </span>
              </button>
            ))}

        {showBoxes &&
          mapping
            .filter((m) => m.w > 0 && m.h > 0)
            .map((m) => {
              const t = titles.get(m.visual_id);
              const bad = problems.has(m.visual_id);
              const active = selected === m.visual_id;
              return (
                <div
                  key={m.visual_id}
                  role="button"
                  tabIndex={0}
                  onPointerDown={(e) => drag(e, m, "move")}
                  onKeyDown={(e) => e.key === "Enter" && onSelect(m.visual_id)}
                  className={`absolute rounded-[14px] cursor-move ${active ? "z-20" : "z-10"}`}
                  style={{
                    left: m.x,
                    top: m.y,
                    width: m.w,
                    height: m.h,
                    outline: `${active ? 4 : 2}px solid ${bad ? "#BA1A1A" : "#F8CF4B"}`,
                    backgroundColor: bad ? "rgba(186, 26, 26, 0.12)" : active ? "rgba(248, 207, 75, 0.18)" : "rgba(248, 207, 75, 0.08)",
                  }}
                >
                  <span
                    className={`absolute -top-3.5 left-3 max-w-[calc(100%-24px)] truncate px-2.5 py-0.5 rounded-full font-code-sm text-[13px] font-semibold shadow-sm ${bad ? "bg-error text-on-error" : "bg-secondary-container text-on-secondary-fixed"}`}
                  >
                    {t?.n} • {t?.title}
                  </span>
                  {active && (
                    <span
                      aria-label="Resize"
                      onPointerDown={(e) => drag(e, m, "resize")}
                      className="absolute -right-2 -bottom-2 w-5 h-5 rounded-full bg-primary-container border-2 border-secondary-container cursor-nwse-resize"
                    />
                  )}
                </div>
              );
            })}
      </div>
    </ScaledCanvas>
  );
}
