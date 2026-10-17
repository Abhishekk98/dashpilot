import { Icon } from "@/components/ui/Icon";
import type { BusinessContext } from "@/lib/api";
import { AUDIENCES, INDUSTRIES } from "@/lib/context";

interface OrganizationCardProps {
  context: BusinessContext;
  onChange: (patch: Partial<BusinessContext>) => void;
  onPolish: () => void;
  polishing: boolean;
  /** Result line under the goals box, e.g. why polishing fell back. */
  polishNote: string | null;
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

const chipBase = "px-4 py-2 rounded-full font-label-md text-label-md transition-all duration-200 flex items-center gap-1.5";
const chipOn = "bg-primary-container text-on-primary shadow-sm";
const chipOff = "bg-surface-container-low text-on-surface-variant hover:bg-surface-container hover:text-on-surface";

/** Left card: company name, industries, audiences and the goals brief. */
export function OrganizationCard({ context, onChange, onPolish, polishing, polishNote }: OrganizationCardProps) {
  return (
    <div className="rounded-card bg-surface-container-lowest/75 backdrop-blur-xl p-7 shadow-card flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3 pb-2">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-secondary-container/40 text-on-surface flex items-center justify-center shrink-0">
            <Icon name="corporate_fare" className="text-[20px]" />
          </div>
          <div>
            <h2 className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight">Organization &amp; Domain</h2>
            <p className="font-body-md text-body-md text-on-surface-variant">Ground DAX formulas and data categorizations in real operational semantics.</p>
          </div>
        </div>
        <span className="hidden sm:inline px-3 py-1 rounded-full bg-surface-container-low font-code-sm text-code-sm text-on-surface-variant shrink-0">
          DAX Auto-Spec
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <label className="font-title-lg text-title-lg text-on-surface flex items-center justify-between gap-3" htmlFor="company-name-input">
          <span>Company / Project Name</span>
          <span className="font-label-sm text-label-sm text-on-surface-variant font-normal">Identifies report header banners</span>
        </label>
        <div className="relative flex items-center">
          <Icon name="domain" className="absolute left-4 text-on-surface-variant text-[20px]" />
          <input
            id="company-name-input"
            type="text"
            maxLength={120}
            value={context.company_name}
            onChange={(e) => onChange({ company_name: e.target.value })}
            placeholder="e.g., Acme Cloud Dynamics or Foodora"
            className="w-full pl-11 pr-10 py-3 rounded-full bg-surface-container-lowest text-on-surface font-body-md text-body-md shadow-sm outline-none transition-all focus:shadow-[0_0_0_3px_rgba(248,207,75,0.45)]"
          />
          {context.company_name && (
            <button
              type="button"
              aria-label="Clear company name"
              onClick={() => onChange({ company_name: "" })}
              className="absolute right-4 text-on-surface-variant hover:text-on-surface"
            >
              <Icon name="cancel" className="text-[18px]" />
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="font-title-lg text-title-lg text-on-surface">Target Industry</span>
          <span className="font-label-sm text-label-sm text-on-surface-variant font-normal text-right">Select primary domains for specialized DAX metrics</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {INDUSTRIES.map((industry) => {
            const on = context.industries.includes(industry);
            return (
              <button
                key={industry}
                type="button"
                aria-pressed={on}
                onClick={() => onChange({ industries: toggle(context.industries, industry) })}
                className={`${chipBase} ${on ? chipOn : chipOff}`}
              >
                {on && <span className="w-2 h-2 rounded-full bg-secondary-container" />}
                <span>{industry}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="font-title-lg text-title-lg text-on-surface">Target Dashboard Audience</span>
          <span className="font-label-sm text-label-sm text-on-surface-variant font-normal text-right">Shapes KPI granularity and executive summaries</span>
        </div>
        <div className="flex flex-wrap gap-2.5">
          {AUDIENCES.map(({ label, icon }) => {
            const on = context.audiences.includes(label);
            return (
              <button
                key={label}
                type="button"
                aria-pressed={on}
                onClick={() => onChange({ audiences: toggle(context.audiences, label) })}
                className={`${chipBase} ${on ? chipOn : chipOff}`}
              >
                {on && <Icon name={icon} className="text-[16px] text-secondary-container" />}
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between gap-3">
          <label className="font-title-lg text-title-lg text-on-surface" htmlFor="goals-textarea">
            Primary Business Goals &amp; North Star Metrics
          </label>
          <span className="hidden sm:inline font-code-sm text-code-sm text-on-surface-variant shrink-0">Natural Language Context</span>
        </div>
        <div className="relative rounded-2xl bg-surface-container-lowest/90 p-4 shadow-sm focus-within:shadow-[0_0_0_3px_rgba(248,207,75,0.4)] transition-all">
          <textarea
            id="goals-textarea"
            rows={4}
            maxLength={2000}
            value={context.goals}
            onChange={(e) => onChange({ goals: e.target.value })}
            placeholder="Describe your primary objectives (e.g. tracking unit economics, regional churn, and courier fulfillment speed)..."
            className="w-full bg-transparent outline-none resize-none font-body-md text-body-md text-on-surface leading-relaxed"
          />
          <div className="flex flex-wrap items-center justify-between gap-2 pt-3 mt-2">
            <div className="flex items-center gap-2 text-on-surface-variant font-code-sm text-code-sm">
              <Icon name={context.goals.trim() ? "verified" : "edit_note"} className="text-[16px] text-secondary" />
              <span>{polishNote ?? (context.goals.trim() ? "DAX semantic prompt ready" : "Add a goal to guide KPI selection")}</span>
            </div>
            <button
              type="button"
              disabled={polishing || !context.goals.trim()}
              onClick={onPolish}
              className="px-4 py-1.5 rounded-full bg-secondary-container text-on-secondary-fixed font-label-sm text-label-sm font-semibold flex items-center gap-1.5 shadow-sm hover:scale-[1.02] active:scale-[0.98] transition-transform disabled:opacity-50 disabled:pointer-events-none"
            >
              <Icon name={polishing ? "sync" : "auto_awesome"} className={`text-[16px] ${polishing ? "animate-spin" : ""}`} />
              <span>{polishing ? "Synthesizing…" : "Polish with AI Co-Analyst"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
