import Link from "next/link";

import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import type { CleaningPlan } from "@/lib/api";
import { downloadJson, formatNumber } from "@/lib/format";

/** Floating action dock at the bottom of the Clean screen. */
export function CleanActionBar({ plan, projectId }: { plan: CleaningPlan | null; projectId: string | null }) {
  const query = projectId ? `?project=${projectId}` : "";
  const exportLog = () =>
    plan &&
    downloadJson(
      {
        accepted: plan.steps.filter((s) => s.status === "accepted"),
        skipped: plan.steps.filter((s) => s.status === "skipped"),
        pending: plan.steps.filter((s) => s.status === "pending"),
        scripts: Object.fromEntries(plan.tables.map((t) => [t.name, t.m_script])),
      },
      "cleaning-log.json",
    );

  return (
    <div className="sticky bottom-4 z-40 mt-8 w-full">
      <div className="w-full p-3 sm:px-6 sm:py-3.5 rounded-panel sm:rounded-full bg-surface-container-lowest/90 backdrop-blur-xl shadow-float flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span className={`w-2.5 h-2.5 rounded-full bg-secondary-container ${plan?.accepted ? "animate-pulse" : ""}`} />
          <span className="font-label-md text-label-md text-on-surface">
            {plan ? (
              <>
                <strong className="font-semibold">
                  {plan.accepted} of {plan.total}
                </strong>{" "}
                transformations applied • {formatNumber(plan.rows_after)} records validated for Star Schema
              </>
            ) : (
              "Loading cleaning plan…"
            )}
          </span>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
          <button
            type="button"
            disabled={!plan}
            onClick={exportLog}
            className="hidden md:flex items-center gap-1.5 px-4 py-2 rounded-full bg-surface-container text-on-surface-variant hover:text-on-surface font-label-md text-label-md transition-colors disabled:opacity-50"
          >
            <Icon name="history_edu" className="text-[16px]" />
            <span>Export Cleaning Log (.json)</span>
          </button>
          <Link
            href={`/project/upload${query}`}
            className="px-4 py-2 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant font-label-md text-label-md transition-colors"
          >
            ← Back: Upload
          </Link>
          {projectId ? (
            <PillButton href={`/project/context${query}`} arrow>
              Next: Business Context
            </PillButton>
          ) : (
            <PillButton arrow disabled>
              Next: Business Context
            </PillButton>
          )}
        </div>
      </div>
    </div>
  );
}
