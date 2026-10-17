"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import {
  type CleaningDecision,
  type CleaningPlan,
  type DiffPreview,
  getCleaningPlan,
  getCleaningPreview,
  getProject,
  type Project,
  saveCleaningDecisions,
} from "@/lib/api";

import { CleanActionBar } from "./CleanActionBar";
import { DiffPreviewCard } from "./DiffPreviewCard";
import { MScriptCard } from "./MScriptCard";
import { SuggestionCard } from "./SuggestionCard";

/** Step 2 screen state: the project's cleaning plan, the active table and its before/after preview. */
export function CleanWorkspace() {
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<CleaningPlan | null>(null);
  const [preview, setPreview] = useState<DiffPreview | null>(null);
  const [activeName, setActiveName] = useState<string | null>(null);
  const [allScripts, setAllScripts] = useState(false);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Ignore preview answers for an older plan or table.
  const previewRequest = useRef(0);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([getProject(projectId), getCleaningPlan(projectId)])
      .then(([p, cleaning]) => {
        setProject(p);
        setPlan(cleaning);
      })
      .catch((e) => setError((e as Error).message || "Could not load the cleaning plan. Is the backend running?"));
  }, [projectId]);

  const tables = plan?.tables ?? [];
  const active = tables.find((t) => t.name === activeName) ?? tables[0];
  const steps = plan?.steps.filter((s) => s.table === active?.name) ?? [];

  const refreshPreview = useCallback((id: string, table: string) => {
    const request = ++previewRequest.current;
    setPreviewLoading(true);
    getCleaningPreview(id, table)
      .then((p) => request === previewRequest.current && setPreview(p))
      .catch((e) => request === previewRequest.current && setError((e as Error).message))
      .finally(() => request === previewRequest.current && setPreviewLoading(false));
  }, []);

  // The script changes whenever the table's accepted steps change, so it doubles as a refresh key.
  const activeTable = active?.name;
  const activeScript = active?.m_script;
  useEffect(() => {
    if (projectId && activeTable) refreshPreview(projectId, activeTable);
  }, [projectId, activeTable, activeScript, refreshPreview]);

  const decide = async (decisions: CleaningDecision[]) => {
    if (!projectId || decisions.length === 0) return;
    const ids = decisions.map((d) => d.step_id);
    setBusy((b) => new Set([...b, ...ids]));
    setError(null);
    try {
      setPlan(await saveCleaningDecisions(projectId, decisions));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy((b) => new Set([...b].filter((id) => !ids.includes(id))));
    }
  };

  if (!projectId) {
    return (
      <div className="flex flex-col w-full">
        <StepHeader step={2} title="Clean Data" />
        <PlaceholderCard
          icon="upload_file"
          title="No project selected"
          description="Upload and profile your data first; cleaning suggestions are built from the Data Quality Report."
        />
        <Link href="/project/upload" className="mt-6 self-center font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
          Go to Step 1: Upload
        </Link>
      </div>
    );
  }

  const pending = plan?.steps.filter((s) => s.status === "pending") ?? [];
  const activeSteps = steps.filter((s) => s.status !== "skipped").length;
  const delta = plan ? plan.score_after - plan.score_before : 0;

  return (
    <div className="flex flex-col w-full">
      <StepHeader
        step={2}
        title={project?.name ?? "Clean Data"}
        projectId={projectId}
        badge={project ? "Draft" : undefined}
        status={
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-lowest/90 backdrop-blur-md shadow-sm font-code-sm text-code-sm text-on-surface-variant">
            <span className="w-2 h-2 rounded-full bg-secondary-container" />
            <span>Power Query M Engine</span>
          </span>
        }
      />

      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-5 mb-6">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2.5">
            <h1 className="font-headline-xl text-headline-xl text-on-surface font-light tracking-tight">Data Cleansing &amp; Heuristics</h1>
            {plan && (
              <span className="px-2.5 py-0.5 rounded-full bg-secondary-container text-on-secondary-fixed font-label-sm text-label-sm uppercase">
                {pending.length} Queued
              </span>
            )}
          </div>
          <p className="font-body-md text-body-md text-on-surface-variant max-w-2xl">
            {plan
              ? `DashPilot identified ${plan.total} cleaning transformations across ${tables.length} ${tables.length === 1 ? "table" : "tables"} to keep the star schema and DAX measures accurate. Accept or skip each one; every accepted step is written as Power Query M.`
              : "Building cleaning suggestions from the Data Quality Report…"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {tables.length > 1 && (
            <div className="flex items-center p-1 rounded-full bg-surface-container-low overflow-x-auto max-w-full">
              {tables.map((t) => {
                const isActive = t.name === active?.name;
                const count = plan?.steps.filter((s) => s.table === t.name).length ?? 0;
                return (
                  <button
                    key={t.name}
                    type="button"
                    onClick={() => setActiveName(t.name)}
                    className={`px-3.5 py-1.5 rounded-full font-label-md text-label-md shrink-0 transition-colors ${
                      isActive ? "bg-primary-container text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface"
                    }`}
                  >
                    {t.name} <span className={`ml-1 ${isActive ? "opacity-75" : "opacity-60"}`}>({count})</span>
                  </button>
                );
              })}
            </div>
          )}
          <button
            type="button"
            onClick={() => setAllScripts((v) => !v)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-surface-container-lowest/90 hover:bg-surface-container-lowest text-on-surface shadow-sm font-label-md text-label-md transition-all"
          >
            <Icon name="terminal" className="text-[16px]" />
            <span>{allScripts ? "Show Active Table Script" : "Preview All M Script"}</span>
          </button>
          <button
            type="button"
            disabled={pending.length === 0}
            onClick={() => decide(pending.map((s) => ({ step_id: s.id, status: "accepted" })))}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary-container hover:opacity-90 text-on-primary font-label-md text-label-md shadow-sm transition-all disabled:opacity-50"
          >
            <Icon name="done_all" className="text-[16px] text-secondary-container" />
            <span>Accept All ({pending.length})</span>
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 w-full items-start">
        <div className="lg:col-span-6 xl:col-span-5 flex flex-col gap-4">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <span className="font-title-lg text-title-lg text-on-surface font-medium">Suggestions</span>
              <span className="px-2 py-0.5 rounded-full bg-surface-container text-on-surface-variant font-label-sm text-label-sm">
                {activeSteps} Active
              </span>
            </div>
            {plan && (
              <div className="flex items-center gap-1.5 text-secondary font-label-md text-label-md">
                <Icon name="verified" className="text-[18px]" />
                <span>
                  Readiness: {plan.score_after}/100{delta > 0 ? ` (+${delta})` : ""}
                </span>
              </div>
            )}
          </div>
          {!plan && !error && <div className="h-48 rounded-panel bg-hatched animate-pulse" />}
          {plan && steps.length === 0 && (
            <div className="p-6 rounded-panel bg-surface-container-lowest/80 shadow-card font-body-md text-body-md text-on-surface-variant">
              No cleaning issues found in {active?.name ?? "this table"}. It can go straight to modelling.
            </div>
          )}
          {steps.map((s) => (
            <SuggestionCard
              key={s.id}
              step={s}
              busy={busy.has(s.id)}
              onStatus={(status) => decide([{ step_id: s.id, status }])}
              onStrategy={(strategy) => decide([{ step_id: s.id, strategy, status: "accepted" }])}
            />
          ))}
        </div>

        <div className="lg:col-span-6 xl:col-span-7 flex flex-col gap-6">
          <DiffPreviewCard preview={preview} loading={previewLoading} />
          {active && <MScriptCard tables={allScripts ? tables : [active]} accepted={allScripts ? (plan?.accepted ?? 0) : active.accepted} />}
        </div>
      </div>

      <CleanActionBar plan={plan} projectId={projectId} />
    </div>
  );
}
