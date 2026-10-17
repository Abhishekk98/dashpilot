import { Icon } from "@/components/ui/Icon";
import type { CleaningStatus, CleaningStep, NullStrategy } from "@/lib/api";
import { TYPE_STYLES, formatNumber } from "@/lib/format";

const STRATEGY_LABELS: Record<NullStrategy, string> = {
  fill_median: "Fill median",
  fill_unknown: "Fill 'Unknown'",
  remove_rows: "Remove rows",
  flag: "Keep blank + flag",
};

interface SuggestionCardProps {
  step: CleaningStep;
  busy: boolean;
  onStatus: (status: CleaningStatus) => void;
  onStrategy: (strategy: NullStrategy) => void;
}

/** One cleaning suggestion: impact tag, include toggle, explanation, evidence and Accept / Skip. */
export function SuggestionCard({ step, busy, onStatus, onStrategy }: SuggestionCardProps) {
  const accepted = step.status === "accepted";
  const skipped = step.status === "skipped";
  const tagClass =
    step.impact === "High"
      ? "bg-secondary-container/30 text-on-secondary-fixed"
      : "bg-surface-container-high text-on-surface-variant";

  return (
    <div
      className={`p-6 rounded-panel bg-surface-container-lowest/80 backdrop-blur-md shadow-card flex flex-col gap-4 relative overflow-hidden transition-opacity ${
        skipped ? "opacity-60" : ""
      } ${busy ? "pointer-events-none" : ""}`}
    >
      {accepted && <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-secondary-container" />}
      <div className="flex items-center justify-between gap-3">
        <span className={`px-3 py-1 rounded-full font-label-sm text-label-sm tracking-wide ${tagClass}`}>
          {step.impact} Impact — {step.category}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={accepted}
          aria-label={accepted ? "Skip this step" : "Accept this step"}
          onClick={() => onStatus(accepted ? "skipped" : "accepted")}
          className={`w-10 h-5 rounded-full p-0.5 flex items-center transition-colors cursor-pointer ${
            accepted ? "bg-secondary-container justify-end" : "bg-surface-container-highest justify-start"
          }`}
        >
          <span className={`w-4 h-4 rounded-full shadow-sm block ${accepted ? "bg-primary-container" : "bg-surface-container-lowest"}`} />
        </button>
      </div>

      <div className="space-y-1.5">
        <h2 className="font-headline-md text-headline-md text-on-surface font-medium tracking-tight break-words">{step.title}</h2>
        <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">{step.description}</p>
      </div>

      <Evidence step={step} />

      {step.strategies.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="Missing-value strategy">
          {step.strategies.map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={step.strategy === s}
              onClick={() => step.strategy !== s && onStrategy(s)}
              className={`px-3 py-1 rounded-full font-label-md text-label-md transition-colors ${
                step.strategy === s
                  ? "bg-secondary-container text-on-secondary-fixed font-semibold"
                  : "bg-surface-container-low text-on-surface-variant hover:text-on-surface"
              }`}
            >
              {STRATEGY_LABELS[s]}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={() => onStatus(accepted ? "pending" : "accepted")}
          className="flex items-center gap-1 px-4 py-1.5 rounded-full bg-primary-container text-on-primary font-label-md text-label-md shadow-sm hover:opacity-90 transition-opacity"
        >
          {accepted && <Icon name="check" className="text-[15px] text-secondary-container" />}
          <span>{accepted ? "Accepted" : "Accept"}</span>
        </button>
        <button
          type="button"
          onClick={() => onStatus(skipped ? "pending" : "skipped")}
          className={`px-4 py-1.5 rounded-full font-label-md text-label-md transition-colors ${
            skipped ? "bg-surface-container-highest text-on-surface" : "bg-surface-container text-on-surface-variant hover:text-on-surface"
          }`}
        >
          {skipped ? "Skipped" : "Skip"}
        </button>
      </div>
    </div>
  );
}

/** Small evidence strip under the description, different per step kind. */
function Evidence({ step }: { step: CleaningStep }) {
  if (step.kind === "standardise_categories") {
    const shown = step.merges.slice(0, 2);
    const more = step.merges.length - shown.length;
    return (
      <div className="flex flex-col gap-1.5">
        {shown.map((m) => (
          <div
            key={m.canonical}
            className="p-2.5 rounded-xl bg-surface-container-low font-code-sm text-code-sm text-on-surface flex items-center justify-between gap-2"
          >
            <span className="text-on-surface-variant line-through decoration-error/50 truncate">
              {Object.entries(m.variants)
                .map(([v, n]) => `'${v}' (${formatNumber(n)})`)
                .join(", ")}
            </span>
            <Icon name="arrow_forward" className="text-[16px] text-secondary shrink-0" />
            <span className="font-semibold text-on-surface bg-surface-container-lowest px-2 py-0.5 rounded shadow-sm shrink-0">
              &apos;{m.canonical}&apos; ({formatNumber(m.total)})
            </span>
          </div>
        ))}
        {more > 0 && (
          <span className="px-1 font-code-sm text-code-sm text-on-surface-variant">
            + {more} more {more === 1 ? "group" : "groups"}
          </span>
        )}
      </div>
    );
  }

  if (step.kind === "set_types") {
    return (
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(step.types).map(([col, type]) => (
          <span key={col} className="px-2.5 py-1 rounded-xl bg-surface-container-low font-code-sm text-code-sm text-on-surface-variant">
            {col} → <span className="text-on-surface font-semibold">{TYPE_STYLES[type].label}</span>
          </span>
        ))}
      </div>
    );
  }

  const label = step.kind === "remove_duplicates" ? "Rows affected" : step.kind === "cast_numeric" ? "Values converted" : "Blank values";
  return (
    <div className="flex items-center gap-2 py-2 px-3 rounded-xl bg-surface-container-low font-code-sm text-code-sm text-on-surface-variant">
      <Icon name="insights" className="text-[16px] text-secondary" />
      <span>
        {label}: {formatNumber(step.rows_affected)} rows ({step.affected_pct.toFixed(2)}%) • Table: {step.table}
      </span>
    </div>
  );
}
