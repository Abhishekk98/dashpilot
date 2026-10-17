import { Icon } from "@/components/ui/Icon";
import type { Insight } from "@/lib/api";

import { InsightChart } from "./InsightChart";

/** Dark hero card for the primary "North Star" insight. */
export function NorthStarCard({ insight, busy, onPin }: { insight: Insight; busy: boolean; onPin: () => void }) {
  const negative = (insight.delta ?? 0) < 0;
  return (
    <article className="p-7 rounded-card bg-primary-container text-on-primary shadow-[0_20px_48px_-12px_rgba(0,0,0,0.3)] flex flex-col gap-5 bg-[radial-gradient(ellipse_80%_60%_at_100%_0%,rgba(248,207,75,0.12),transparent_70%)]">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-3 py-1 rounded-full bg-secondary-container text-on-secondary-fixed font-label-sm text-label-sm font-semibold uppercase">Primary North Star Insight</span>
            <span className="px-2.5 py-0.5 rounded-full bg-inverse-surface font-code-sm text-code-sm text-on-primary-container">
              Confidence: {(insight.confidence * 100).toFixed(1)}%
            </span>
          </div>
          <span className="font-code-sm text-code-sm text-on-primary-container">Source: {insight.sources.join(" × ")}</span>
        </div>
        <button
          type="button"
          onClick={onPin}
          disabled={busy}
          aria-pressed={insight.pinned}
          title={insight.pinned ? "Pinned to the dashboard" : "Pin to the dashboard's Key Insights card"}
          className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${insight.pinned ? "bg-secondary-container text-on-secondary-fixed" : "bg-inverse-surface text-inverse-on-surface hover:bg-outline"}`}
        >
          <Icon name="push_pin" className="text-[18px]" />
        </button>
      </div>
      <h2 className="font-headline-md text-headline-md text-on-primary font-semibold tracking-tight leading-snug">{insight.headline}</h2>
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="font-metric-huge-mobile text-metric-huge-mobile lg:font-metric-huge lg:text-metric-huge text-secondary-container font-light tracking-tight">
          {insight.delta_text && insight.type === "comparison" ? insight.delta_text : insight.value_text}
        </span>
        <span className={`px-2.5 py-1 rounded-full font-code-sm text-code-sm font-semibold ${negative ? "bg-error-container text-on-error-container" : "bg-secondary-container text-on-secondary-fixed"}`}>
          {insight.type === "comparison" ? insight.value_text : insight.delta_text}
        </span>
      </div>
      <p className="font-body-md text-body-md text-on-primary-container leading-relaxed">{insight.body}</p>
      <div className="p-4 rounded-[20px] bg-inverse-surface/70">
        <InsightChart insight={insight} dark />
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <p className="flex items-start gap-2 font-body-md text-body-md text-on-primary">
          <Icon name="lightbulb" className="text-[18px] text-secondary-container shrink-0" />
          <span>
            <span className="text-secondary-container font-semibold">Recommended Action: </span>
            {insight.action}
          </span>
        </p>
        <button
          type="button"
          onClick={onPin}
          disabled={busy}
          className="px-4 py-2 rounded-full bg-secondary-container text-on-secondary-fixed font-label-md text-label-md font-semibold flex items-center gap-1.5 shrink-0"
        >
          {insight.pinned ? "On Dashboard KPI Card" : "Add to Dashboard KPI Card"}
          <Icon name={insight.pinned ? "check" : "add"} className="text-[16px]" />
        </button>
      </div>
    </article>
  );
}
