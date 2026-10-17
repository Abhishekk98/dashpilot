"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import {
  deleteMeasure,
  getMeasures,
  getProject,
  type MeasureInput,
  type MeasurePlan,
  measuresTmdlUrl,
  polishMeasure,
  type Project,
  resetMeasure,
  saveMeasure,
  suggestMeasures,
  validateMeasures,
} from "@/lib/api";

import { KpiCards } from "./KpiCards";
import { MeasureInspector } from "./MeasureInspector";
import { MeasureList } from "./MeasureList";

/** Step 5 screen state: the measure plan, the selected measure and the AI actions. */
export function KpisWorkspace() {
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<MeasurePlan | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([getProject(projectId), getMeasures(projectId)])
      .then(([p, m]) => {
        setProject(p);
        setPlan(m);
        setSelected((s) => s ?? m.measures.find((x) => x.name.endsWith("YoY %"))?.name ?? m.measures[0]?.name ?? null);
      })
      .catch((e) => setError((e as Error).message || "Could not build the measures. Is the backend running?"));
  }, [projectId]);

  /** Run an action that returns a fresh plan; keeps the selection when the measure still exists. */
  const run = useCallback(async (action: () => Promise<MeasurePlan>, select?: string) => {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setPlan(next);
      if (select !== undefined) setSelected(select);
      else setSelected((s) => (s && next.measures.some((m) => m.name === s) ? s : (next.measures[0]?.name ?? null)));
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  if (!projectId) {
    return (
      <div className="flex flex-col w-full">
        <StepHeader step={5} title="KPIs & DAX" />
        <PlaceholderCard icon="upload_file" title="No project selected" description="Upload data and build the model first; measures are generated from the data model." />
        <Link href="/project/upload" className="mt-6 self-center font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
          Go to Step 1: Upload
        </Link>
      </div>
    );
  }

  const measure = plan?.measures.find((m) => m.name === selected) ?? null;
  const generated = Boolean(measure && (measure.source === "library" || measure.source === "rules"));
  const total = plan?.measures.length ?? 0;
  const health = plan && total ? Math.round(((total - plan.errors) / total) * 100) : 100;

  const handleSave = async (data: MeasureInput, original?: string) => {
    const ok = await run(() => saveMeasure(projectId, data, original), data.name.replace(/^\[|\]$/g, "").trim());
    if (ok) setCreating(false);
    return ok;
  };

  const handleSuggest = async () => {
    setSuggesting(true);
    await run(() => suggestMeasures(projectId));
    setSuggesting(false);
  };

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={5} title={project?.name ?? "KPIs & DAX"} projectId={projectId} badge={project ? "Draft" : undefined} />

      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 pb-2 mb-8">
        <div className="flex flex-col gap-2 max-w-2xl">
          <div className="flex flex-wrap items-center gap-3">
            <span className="px-3 py-1 rounded-full bg-secondary-container/30 text-secondary font-label-sm text-label-sm uppercase tracking-wider font-semibold">
              Semantic Layer Orchestrator
            </span>
            <span className="font-code-sm text-code-sm text-on-surface-variant">TMDL / DAX Engine</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-primary font-light tracking-tight">KPIs &amp; DAX Formula Studio</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            {plan
              ? `DashPilot synthesized ${total} production-grade DAX measures${plan.industries.length ? ` for ${plan.industries.join(" & ")}` : ""}, validated against your cleaned data.`
              : "Generating measures from your data model…"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {plan?.ai_status === "available" && (
            <button
              type="button"
              disabled={busy}
              onClick={handleSuggest}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-secondary-container text-on-secondary-fixed shadow-sm font-label-md text-label-md font-semibold disabled:opacity-60"
            >
              <Icon name={suggesting ? "sync" : "auto_awesome"} className={`text-[16px] ${suggesting ? "animate-spin" : ""}`} />
              <span>{suggesting ? "Asking AI Co-Analyst…" : "Suggest Measures from Goals"}</span>
            </button>
          )}
          {plan?.test_context && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-surface-container-lowest/80 backdrop-blur-md shadow-sm">
              <span className="w-2 h-2 rounded-full bg-secondary-container" />
              <span className="font-label-md text-label-md text-on-surface font-medium">Time intelligence: {plan.test_context}</span>
            </div>
          )}
          {plan && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-surface-container-lowest/80 backdrop-blur-md shadow-sm">
              <Icon name={plan.errors ? "error" : "verified"} className={`text-[16px] ${plan.errors ? "text-coral" : "text-secondary"}`} />
              <span className="font-label-md text-label-md text-on-surface font-medium">
                Formula Health: {health}% Passed ({plan.errors} {plan.errors === 1 ? "Error" : "Errors"})
              </span>
            </div>
          )}
        </div>
      </section>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}
      {plan && plan.notes.length > 0 && (
        <div role="status" className="mb-6 p-4 rounded-inner bg-surface-container-lowest/80 shadow-card flex flex-col gap-1.5">
          {plan.notes.map((n) => (
            <p key={n} className="flex items-start gap-2 font-body-md text-xs text-on-surface">
              <Icon name="auto_awesome" className="text-[16px] text-secondary shrink-0" />
              <span>{n}</span>
            </p>
          ))}
        </div>
      )}

      {plan ? <KpiCards cards={plan.cards} onSelect={(n) => { setCreating(false); setSelected(n); }} /> : !error && <div className="h-40 rounded-card bg-hatched animate-pulse mb-8" />}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start mb-8">
        <div className="lg:col-span-7">
          {plan && (
            <MeasureList
              measures={plan.measures}
              folders={plan.folders}
              selected={creating ? null : selected}
              busy={busy}
              onSelect={(n) => {
                setCreating(false);
                setSelected(n);
              }}
              onNew={() => setCreating(true)}
              onValidate={() => run(() => validateMeasures(projectId))}
            />
          )}
        </div>
        <div className="lg:col-span-5 lg:sticky lg:top-28">
          {plan && (
            <MeasureInspector
              measure={creating ? null : measure}
              creating={creating}
              generated={generated}
              busy={busy}
              aiAvailable={plan.ai_status === "available"}
              onSave={handleSave}
              onCancelNew={() => setCreating(false)}
              onRegenerate={() => measure && run(() => resetMeasure(projectId, measure.name), measure.name)}
              onDelete={() => measure && run(() => deleteMeasure(projectId, measure.name))}
              onPolish={() => measure && run(() => polishMeasure(projectId, measure.name), measure.name)}
            />
          )}
        </div>
      </div>

      <div className="sticky bottom-4 z-40 w-full">
        <div className="p-5 md:px-8 rounded-panel bg-surface-container-lowest/90 backdrop-blur-xl shadow-[0_16px_40px_-8px_rgba(35,35,35,0.18)] flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className={`w-2.5 h-2.5 rounded-full ${plan?.errors ? "bg-coral" : "bg-secondary-container"}`} />
            <div className="flex flex-col">
              <span className="font-title-lg text-title-lg text-on-surface font-semibold">Step 5 of 9 {plan && !plan.errors ? "Complete" : ""}</span>
              <span className="font-body-md text-body-md text-on-surface-variant">
                {plan
                  ? `${total} Measures Compiled • ${plan.errors ? `${plan.errors} need fixing` : "Zero Circular References"} • ${plan.edge} to check in Power BI`
                  : "Compiling measures…"}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 justify-end">
            <Link
              href={`/project/model?project=${projectId}`}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md transition-all flex items-center gap-1.5"
            >
              <Icon name="arrow_back" className="text-[16px]" />
              Back: Data Model
            </Link>
            <a
              href={measuresTmdlUrl(projectId)}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md transition-all flex items-center gap-1.5"
            >
              <Icon name="file_download" className="text-[16px]" />
              Export DAX Script (.tmdl)
            </a>
            <PillButton href={`/project/insights?project=${projectId}`} arrow>
              Next: AI Insights &amp; Narratives
            </PillButton>
          </div>
        </div>
      </div>
    </div>
  );
}
