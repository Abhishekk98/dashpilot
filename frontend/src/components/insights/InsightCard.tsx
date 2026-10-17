import { Icon } from "@/components/ui/Icon";
import type { Insight } from "@/lib/api";

import { InsightChart } from "./InsightChart";

export const TYPE_LABELS: Record<Insight["type"], string> = {
  trend: "Trend",
  comparison: "Period Comparison",
  anomaly: "Anomaly",
  top_performer: "Top Performer",
  contribution: "Pareto",
  rate_alert: "Rate Alert",
  answer: "Your Question",
};

const TYPE_TONES: Record<Insight["type"], string> = {
  trend: "bg-secondary-container/40 text-on-secondary-container",
  comparison: "bg-surface-container-high text-on-surface",
  anomaly: "bg-error-container text-on-error-container",
  top_performer: "bg-secondary-container/40 text-on-secondary-container",
  contribution: "bg-surface-container-high text-on-surface",
  rate_alert: "bg-error-container text-on-error-container",
  answer: "bg-primary-container text-on-primary",
};

interface InsightCardProps {
  insight: Insight;
  busy: boolean;
  onPin: () => void;
  onRemove?: () => void;
}

/** Light insight card with a mini chart, the narrative and the recommended action. */
export function InsightCard({ insight, busy, onPin, onRemove }: InsightCardProps) {
  const negative = (insight.delta ?? 0) < 0;
  return (
    <article className="p-6 rounded-card bg-surface-container-lowest/80 backdrop-blur-md shadow-card flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`px-2.5 py-0.5 rounded-full font-label-sm text-label-sm font-semibold shrink-0 ${TYPE_TONES[insight.type]}`}>{TYPE_LABELS[insight.type]}</span>
          <span className="font-label-sm text-label-sm text-on-surface-variant truncate">{insight.dimension ? insight.dimension.split("[")[1]?.replace("]", "").replace(/_/g, " ") : insight.measure}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {onRemove && (
            <button type="button" onClick={onRemove} disabled={busy} aria-label="Remove this answer" className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:text-error">
              <Icon name="close" className="text-[16px]" />
            </button>
          )}
          <button
            type="button"
            onClick={onPin}
            disabled={busy}
            aria-pressed={insight.pinned}
            title={insight.pinned ? "Pinned to the dashboard's Key Insights card" : "Pin to the dashboard's Key Insights card"}
            className={`w-7 h-7 rounded-full flex items-center justify-center ${insight.pinned ? "bg-secondary-container text-on-secondary-fixed" : "text-on-surface-variant hover:text-on-surface"}`}
          >
            <Icon name={insight.pinned ? "bookmark_added" : "bookmark"} className="text-[16px]" />
          </button>
        </div>
      </div>
      <h3 className="font-title-lg text-title-lg text-on-surface font-medium leading-snug">{insight.headline}</h3>
      <div className="flex items-baseline gap-2">
        <span className="font-headline-lg text-headline-lg text-primary font-light tracking-tight">{insight.value_text}</span>
        {insight.delta_text && (
          <span className={`font-code-sm text-code-sm ${negative ? "text-error" : "text-secondary"}`}>{insight.delta_text}</span>
        )}
      </div>
      <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">{insight.body}</p>
      <div className="p-3 rounded-2xl bg-surface-container-low">
        <InsightChart insight={insight} />
      </div>
      <div className="flex items-start gap-2 font-body-md text-xs text-on-surface">
        <Icon name="lightbulb" className="text-[16px] text-secondary shrink-0" />
        <span>{insight.action}</span>
      </div>
      <div className="flex items-center justify-between gap-2 pt-1 font-code-sm text-[10px] text-on-surface-variant">
        <span>Confidence {(insight.confidence * 100).toFixed(0)}% • {insight.narrative_source === "ai" ? "AI narrative (grounded)" : "Computed narrative"}</span>
        <span className="truncate">{insight.sources.join(" × ")}</span>
      </div>
    </article>
  );
}
