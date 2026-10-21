"use client";

import { useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { DashboardPlan, PlanVisual } from "@/lib/api";

import { ScaledCanvas } from "./ScaledCanvas";
import { TYPE_ICONS, TYPE_LABELS } from "./visualTypes";

const ROLE_STYLES: Record<PlanVisual["role"], string> = {
  slicer: "bg-surface-container-lowest border-outline-variant/60 rounded-full",
  kpi: "bg-surface-container-lowest border-outline-variant/40",
  chart: "bg-surface-container-lowest border-outline-variant/40",
  insights: "bg-secondary-container/25 border-secondary-container",
};

/** 1280x720 wireframe of the plan's boxes, scaled to fit. */
export function PlanWireframe({ plan, highlight, onPick }: { plan: DashboardPlan; highlight: string | null; onPick: (id: string) => void }) {
  const pages = plan.pages && plan.pages.length > 0 ? plan.pages : ["Overview"];
  const [activePage, setActivePage] = useState<number>(1);
  const curPage = Math.min(activePage, pages.length);
  const visibleVisuals = plan.visuals.filter((v) => v.role === "slicer" || (v.page ?? 1) === curPage);

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-1.5 p-1 rounded-full bg-surface-container-low">
          {pages.map((pName, idx) => {
            const pageNum = idx + 1;
            const active = curPage === pageNum;
            return (
              <button
                key={pageNum}
                type="button"
                onClick={() => setActivePage(pageNum)}
                className={`px-3.5 py-1 rounded-full font-label-sm text-xs transition-colors ${
                  active
                    ? "bg-surface-container-highest text-on-surface font-semibold shadow-xs"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                Page {pageNum}: {pName}
              </button>
            );
          })}
        </div>
        <span className="font-body-md text-[11px] text-on-surface-variant/80 flex items-center gap-1.5">
          <Icon name="info" className="text-[14px] text-secondary" />
          Neutral preview, the final layout comes from the design you pick
        </span>
      </div>

      <ScaledCanvas className="rounded-inner bg-surface-container-low shadow-card">
        <div className="relative w-[1280px] h-[720px] bg-hatched-neutral/30">
          <div className="absolute left-6 top-4 h-11 flex flex-col justify-center">
            <span className="font-headline-md text-[22px] text-on-surface font-semibold tracking-tight">{plan.title}</span>
            <span className="font-body-md text-[12px] text-on-surface-variant">
              {curPage === 1 ? (plan.subtitle || "Executive overview") : (pages[curPage - 1] || "Details")}
            </span>
          </div>
          {visibleVisuals.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => onPick(v.id)}
              className={`absolute border-2 rounded-[14px] text-left px-4 py-3 flex flex-col gap-1 overflow-hidden transition-shadow ${ROLE_STYLES[v.role]} ${highlight === v.id ? "ring-4 ring-secondary-container" : ""}`}
              style={{ left: v.box.x, top: v.box.y, width: v.box.w, height: v.box.h }}
            >
              <span className="flex items-center gap-2 font-title-lg text-[15px] text-on-surface font-semibold leading-tight">
                <Icon name={TYPE_ICONS[v.type] ?? "widgets"} className="text-[20px] text-on-surface-variant" />
                <span className="truncate">{v.title}</span>
              </span>
              {v.role !== "slicer" && (
                <span className="font-code-sm text-[12px] text-on-surface-variant truncate">
                  {TYPE_LABELS[v.type] ?? v.type}
                  {v.measures.length > 0 && ` · ${v.measures.join(", ")}`}
                </span>
              )}
              {v.role === "insights" && (
                <ul className="mt-1 list-disc pl-5 font-body-md text-[12px] text-on-surface leading-snug">
                  {v.text.slice(0, 3).map((t) => (
                    <li key={t} className="line-clamp-2">{t}</li>
                  ))}
                </ul>
              )}
            </button>
          ))}
        </div>
      </ScaledCanvas>
    </div>
  );
}
