import { Icon } from "@/components/ui/Icon";
import { PillTag } from "@/components/ui/PillTag";
import type { FidelityReport as Report } from "@/lib/api";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

/** Design fidelity: how exactly the Power BI page reproduces the design, overall and per card. */
export function FidelityReport({ report, override, onOverride, busy }: { report: Report; override: boolean; onOverride?: (v: boolean) => void; busy?: boolean }) {
  const failing = report.cards.filter((c) => !c.passed);
  const worst = [...report.cards].sort((a, b) => a.score - b.score).slice(0, 6);
  return (
    <div className={`p-4 rounded-2xl flex flex-col gap-3 ${report.passed ? "bg-surface-container-low" : override ? "bg-secondary-container/25" : "bg-error-container/40 ring-2 ring-error/50"}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="font-title-lg text-title-lg text-on-surface font-semibold flex items-center gap-2">
          <Icon name={report.passed ? "verified" : "rule"} className="text-[20px]" /> Design fidelity
        </span>
        <PillTag tone={report.passed ? "success" : override ? "warning" : "error"} size="md">
          {pct(report.overall)} {report.passed ? "match" : override ? "accepted" : `< ${pct(report.threshold)}`}
        </PillTag>
      </div>
      <p className="font-body-md text-xs text-on-surface-variant">
        Everything outside the visual areas is compared with {report.reference === "screenshot" ? "Stitch's own screen.png" : "the design's own render"}; inside them Power BI draws the real visuals.
        {report.render_match !== null && ` Our render of the HTML matches Stitch's screenshot ${pct(report.render_match)}.`}
      </p>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
        {worst.map((c) => (
          <li key={c.box_id} className={`flex items-center justify-between gap-2 px-2.5 py-1 rounded-lg font-code-sm text-code-sm ${c.passed ? "bg-surface-container-lowest" : "bg-error-container text-on-error-container"}`}>
            <span className="truncate">{c.title}</span>
            <span className="shrink-0">{pct(c.score)}</span>
          </li>
        ))}
      </ul>
      {report.notes.map((n) => (
        <p key={n} className="flex items-start gap-1.5 font-body-md text-xs text-on-surface">
          <Icon name="info" className="text-[14px] shrink-0 mt-0.5" /> {n}
        </p>
      ))}
      {!report.passed && onOverride && (
        <label className="flex items-start gap-2 font-body-md text-xs text-on-surface cursor-pointer">
          <input type="checkbox" checked={override} disabled={busy} onChange={(e) => onOverride(e.target.checked)} className="mt-0.5 accent-secondary" />
          <span>
            Build anyway: I accept that the Power BI page will differ from the design{failing.length ? ` (${failing.length} card${failing.length > 1 ? "s" : ""} below ${pct(report.card_threshold)})` : ""}. The build stays blocked until this is checked.
          </span>
        </label>
      )}
    </div>
  );
}
