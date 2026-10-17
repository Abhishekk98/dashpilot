import { Icon } from "@/components/ui/Icon";
import type { KpiCard } from "@/lib/api";

/** Sparkline path for a series of values, scaled into a 64x16 box. */
function sparkPath(values: number[]): string | null {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((v, i) => `${i === 0 ? "M" : "L"} ${((i / (values.length - 1)) * 62 + 1).toFixed(1)} ${(15 - ((v - min) / span) * 13).toFixed(1)}`)
    .join(" ");
}

/** "Executive KPI Row": the five headline measures with their calculated values. */
export function KpiCards({ cards, onSelect }: { cards: KpiCard[]; onSelect: (name: string) => void }) {
  if (cards.length === 0) return null;
  return (
    <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-8">
      {cards.map((c) => {
        const path = sparkPath(c.spark);
        return (
          <button
            key={c.name}
            type="button"
            onClick={() => onSelect(c.name)}
            className="p-6 rounded-panel bg-surface-container-lowest/80 backdrop-blur-md shadow-card flex flex-col justify-between text-left hover:scale-[1.01] transition-all min-w-0"
          >
            <span className="flex flex-col gap-3 min-w-0">
              <span className="flex items-center justify-between gap-2">
                <span className="font-label-md text-label-md text-on-surface-variant truncate">{c.name}</span>
                <span className="w-6 h-6 rounded-full bg-secondary-container flex items-center justify-center text-on-secondary-fixed shrink-0">
                  <Icon name={c.accent ? "bolt" : "check"} className="text-[14px]" />
                </span>
              </span>
              <span
                title={c.value_text}
                className={`font-metric-huge-mobile text-metric-huge-mobile 2xl:font-metric-huge 2xl:text-metric-huge tracking-tight font-light truncate ${c.accent ? "text-secondary" : "text-primary"}`}
              >
                {c.value_text}
              </span>
            </span>
            <span className="mt-4 pt-3 flex items-center justify-between gap-2">
              <span
                className={`px-2.5 py-0.5 rounded-full font-code-sm text-code-sm font-medium truncate ${c.accent ? "bg-secondary-container/40 text-on-secondary-container" : "bg-surface-container text-on-surface"}`}
              >
                {c.badge}
              </span>
              {path && (
                <svg className="w-16 h-4 text-secondary-container shrink-0" fill="none" viewBox="0 0 64 16" aria-hidden="true">
                  <path d={path} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                </svg>
              )}
            </span>
          </button>
        );
      })}
    </section>
  );
}
