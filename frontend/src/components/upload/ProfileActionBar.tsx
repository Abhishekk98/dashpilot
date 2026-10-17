import { PillButton } from "@/components/ui/PillButton";
import type { QualityReport } from "@/lib/api";
import { downloadJson, formatNumber } from "@/lib/format";

/** "Sticky-Feel Fluid Action Bar" at the bottom of the Upload screen. */
export function ProfileActionBar({ report, nextHref }: { report: QualityReport | null; nextHref: string | null }) {
  const tables = report?.tables.length ?? 0;
  return (
    <section className="rounded-panel bg-surface-container-lowest/90 backdrop-blur-2xl p-4 md:px-6 md:py-4 shadow-[0_16px_40px_-8px_rgba(35,35,35,0.08)] flex flex-col sm:flex-row items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className={`w-3 h-3 rounded-full bg-secondary-container ${tables ? "animate-pulse" : ""}`} />
        <div className="flex flex-col">
          <span className="font-body-md text-body-md font-semibold text-on-surface leading-snug">
            {tables
              ? `${tables} ${tables === 1 ? "table" : "tables"} parsed • ${formatNumber(report!.total_rows)} total records • ${report!.total_columns} columns profiled`
              : "Waiting for data"}
          </span>
          <span className="font-code-sm text-code-sm text-on-surface-variant">
            {tables ? "Ready for automated cleaning and missing-value handling" : "Upload at least one CSV or Excel file to continue"}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
        <PillButton
          variant="secondary"
          icon="data_object"
          disabled={!tables}
          onClick={() => report && downloadJson(report, "data-quality-summary.json")}
        >
          Export Summary (.json)
        </PillButton>
        {nextHref && tables ? (
          <PillButton href={nextHref} arrow>
            Next: Clean Data
          </PillButton>
        ) : (
          <PillButton arrow disabled>
            Next: Clean Data
          </PillButton>
        )}
      </div>
    </section>
  );
}
