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
  return (
    <ScaledCanvas className="rounded-inner bg-surface-container-low shadow-card">
      <div className="relative w-[1280px] h-[720px] bg-hatched-neutral/30">
        <div className="absolute left-6 top-4 h-11 flex flex-col justify-center">
          <span className="font-headline-md text-[22px] text-on-surface font-semibold tracking-tight">{plan.title}</span>
          <span className="font-body-md text-[12px] text-on-surface-variant">{plan.subtitle}</span>
        </div>
        {plan.visuals.map((v) => (
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
  );
}
