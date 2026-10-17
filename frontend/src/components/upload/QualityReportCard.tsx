import { Icon } from "@/components/ui/Icon";
import { PillTag, type PillTagTone } from "@/components/ui/PillTag";
import { QualityGauge } from "@/components/ui/QualityGauge";
import type { QualityReport } from "@/lib/api";
import { formatNumber, formatPct } from "@/lib/format";

const AI_BADGE: Record<QualityReport["ai_status"], { label: string; tone: PillTagTone }> = {
  off: { label: "Rule-based Profiler", tone: "warning" },
  pending: { label: "AI Refining Roles…", tone: "warning" },
  done: { label: "AI Profiler Active", tone: "warning" },
  failed: { label: "Rule-based (AI unavailable)", tone: "neutral" },
};

interface QualityReportCardProps {
  report: QualityReport | null;
  loading: boolean;
  /** Active provider name for the "refining" note, e.g. "Gemini". */
  providerName: string;
}

/** Right card of the Upload screen: overall score, per-table readiness and the schema signal. */
export function QualityReportCard({ report, loading, providerName }: QualityReportCardProps) {
  const empty = !report || report.tables.length === 0;
  // Before the first report arrives the badge follows the loading state instead of guessing.
  const badge = report ? AI_BADGE[report.ai_status] : { label: loading ? "Profiling…" : "Profiler Idle", tone: "warning" as const };
  const refining = !loading && report?.ai_status === "pending";

  return (
    <div className="lg:col-span-5 flex flex-col justify-between rounded-card bg-surface-container-lowest/75 backdrop-blur-xl p-7 shadow-card">
      <div>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <span className="font-title-lg text-title-lg font-semibold text-on-surface">Data Quality Report</span>
            <div className="w-7 h-7 rounded-full bg-secondary-container text-on-secondary-fixed flex items-center justify-center font-code-sm font-bold">
              ↗
            </div>
          </div>
          <PillTag tone={badge.tone} dot size="md" className={refining ? "animate-pulse" : ""}>
            {badge.label}
          </PillTag>
        </div>

        {refining && (
          <div role="status" className="mb-5 px-4 py-3 rounded-inner bg-surface-container-low/70 flex flex-col gap-2">
            <div className="h-1.5 w-full rounded-full bg-hatched animate-pulse" />
            <p className="font-body-md text-xs text-on-surface-variant">
              Rule-based results are ready. {providerName} is refining semantic roles for{" "}
              {formatNumber(report.total_columns)} columns; large workbooks can take up to a minute.
            </p>
          </div>
        )}
        {!loading && report?.ai_status === "failed" && report.ai_note && (
          <p className="mb-5 px-4 py-2.5 rounded-inner bg-surface-container-low/70 font-body-md text-xs text-on-surface-variant">
            AI refinement skipped: {report.ai_note.replace(/\.$/, "")}. Showing rule-based roles.
          </p>
        )}

        <div className="flex items-center gap-6 p-5 rounded-[22px] bg-surface-container-low/70 mb-5">
          <QualityGauge value={empty ? 0 : report.score} />
          <div className="flex flex-col">
            {loading ? (
              <>
                <div className="h-2 w-40 rounded-full bg-hatched animate-pulse mb-2" />
                <p className="font-body-md text-body-md text-on-surface-variant">Profiling your data…</p>
              </>
            ) : empty ? (
              <>
                <p className="font-body-md text-body-md text-on-surface font-medium leading-snug">No data profiled yet.</p>
                <p className="font-body-md text-xs text-on-surface-variant mt-0.5">
                  Upload a file to get a quality score, column types and semantic roles.
                </p>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2 mb-1">
                  <PillTag tone={report.label === "Needs Attention" ? "error" : "accent"}>
                    {report.label}
                  </PillTag>
                  <span className="font-code-sm text-code-sm text-on-surface-variant">
                    Confidence {formatPct(report.confidence)}
                  </span>
                </div>
                <p className="font-body-md text-body-md text-on-surface font-medium leading-snug">{report.headline}</p>
                <p className="font-body-md text-xs text-on-surface-variant mt-0.5">{report.detail}</p>
              </>
            )}
          </div>
        </div>

        {!empty && (
          <div className="flex flex-col gap-2.5 mb-5">
            <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-semibold px-1">
              Per-Table Readiness
            </span>
            {report.tables.map((t) => {
              const nullTone = t.null_pct < 1 ? "success" : "warning";
              const dupTone = t.duplicate_rows === 0 ? "success" : "warning";
              return (
                <div key={t.name} className="p-3.5 rounded-[18px] bg-surface-container-lowest flex items-center justify-between shadow-xs gap-3">
                  <div className="flex flex-col min-w-0">
                    <span className="font-body-md text-body-md font-semibold text-on-surface truncate">{t.name}</span>
                    <span className="font-code-sm text-code-sm text-on-surface-variant">
                      {formatNumber(t.rows)} rows • {t.columns} {t.columns === 1 ? "column" : "columns"}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <PillTag mono tone={nullTone}>{formatPct(t.null_pct)} Nulls</PillTag>
                    <PillTag mono tone={dupTone}>{formatNumber(t.duplicate_rows)} Dups</PillTag>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {!empty && (
        <div className="p-4 rounded-inner bg-primary-container text-on-primary shadow-sm flex items-start gap-3">
          <div className="w-7 h-7 rounded-full bg-secondary-container text-on-secondary-fixed flex items-center justify-center shrink-0 mt-0.5">
            <Icon name="neurology" className="text-[16px]" />
          </div>
          <div className="flex flex-col">
            <span className="font-label-sm text-label-sm text-secondary-container uppercase tracking-wider font-semibold">
              Profiler Schema Signal
            </span>
            <p className="font-body-md text-body-md text-on-primary/90 leading-snug">{report.signal}</p>
          </div>
        </div>
      )}
    </div>
  );
}
