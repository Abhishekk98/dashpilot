"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import { getModel, getProject, type ModelPlan, type ModelSettings, type Project, saveModelSettings, tmdlZipUrl } from "@/lib/api";

import { ModelSidePanel } from "./ModelSidePanel";
import { SchemaDiagram } from "./SchemaDiagram";

const ZOOMS = [0.5, 0.6, 0.75, 0.9, 1, 1.1, 1.25];

/** Step 4 screen state: the project's data model, the user's settings and the diagram view. */
export function ModelWorkspace() {
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<ModelPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [showFilters, setShowFilters] = useState(false);
  const frame = useRef<HTMLDivElement>(null);
  // Ignore an AI answer that arrives after the user already changed the model.
  const version = useRef(0);

  useEffect(() => {
    if (!projectId) return;
    const v = ++version.current;
    Promise.all([getProject(projectId), getModel(projectId, false)])
      .then(([p, m]) => {
        setProject(p);
        setPlan(m);
        if (m.ai_status === "pending") {
          // Phase 2: AI review of fact/dimension roles, shown in place when it lands.
          getModel(projectId, true)
            .then((refined) => v === version.current && setPlan(refined))
            .catch(() => undefined);
        }
      })
      .catch((e) => setError((e as Error).message || "Could not build the model. Is the backend running?"));
  }, [projectId]);

  const update = useCallback(
    async (change: (s: ModelSettings) => ModelSettings) => {
      if (!projectId || !plan) return;
      version.current++;
      setBusy(true);
      setError(null);
      try {
        setPlan(await saveModelSettings(projectId, change(plan.settings)));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [projectId, plan],
  );

  const validate = async () => {
    if (!projectId) return;
    setBusy(true);
    try {
      setPlan(await getModel(projectId, false));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!projectId) {
    return (
      <div className="flex flex-col w-full">
        <StepHeader step={4} title="Data Model" />
        <PlaceholderCard icon="upload_file" title="No project selected" description="Upload, profile and clean your data first; the model is built from the cleaned tables." />
        <Link href="/project/upload" className="mt-6 self-center font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
          Go to Step 1: Upload
        </Link>
      </div>
    );
  }

  const override = (table: string, patch: { included?: boolean; kind?: "fact" | "dimension" }) =>
    update((s) => ({ ...s, table_overrides: { ...s.table_overrides, [table]: { ...s.table_overrides[table], ...patch } } }));

  const removeRelationship = (id: string) =>
    update((s) => {
      const added = s.added_relationships.filter((r) => `${r.from_table}.${r.from_column}->${r.to_table}.${r.to_column}` !== id);
      return added.length !== s.added_relationships.length
        ? { ...s, added_relationships: added }
        : { ...s, removed_relationships: [...s.removed_relationships, id] };
    });

  const fit = () => {
    const box = frame.current;
    const inner = box?.firstElementChild as HTMLElement | null;
    if (!box || !inner) return;
    const ratio = (box.clientWidth / (inner.scrollWidth * (1 / zoom))) * 0.98;
    setZoom(ZOOMS.reduce((best, z) => (z <= ratio && z > best ? z : best), ZOOMS[0]));
  };
  const step = (dir: 1 | -1) => setZoom((z) => ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, ZOOMS.indexOf(z) + dir))] ?? 1);

  const excluded = plan?.tables.filter((t) => !t.included) ?? [];
  const problems = plan ? plan.relationships.filter((r) => !r.valid).length + plan.tmdl_errors.length : 0;
  const auto = plan
    ? Object.keys(plan.settings.table_overrides).length === 0 && plan.settings.removed_relationships.length === 0 && plan.settings.added_relationships.length === 0
    : true;

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={4} title={project?.name ?? "Data Model"} projectId={projectId} badge={project ? "Draft" : undefined} />

      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 mb-6">
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-3 py-1 rounded-full bg-surface-container-high/70 text-on-surface-variant font-label-sm text-label-sm tracking-wider uppercase">
              Pipeline Phase IV • Semantic Data Model
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-secondary-container/30 text-on-secondary-container font-label-sm text-label-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary" />
              Power BI VertiPaq Profile
            </span>
          </div>
          <h1 className="font-headline-xl text-headline-xl tracking-tight text-on-surface font-light">Data Model &amp; Star Schema</h1>
          <p className="font-body-md text-body-md text-on-surface-variant max-w-3xl">
            DashPilot auto-configured a Star Schema from your cleaned tables, optimized for the Power BI VertiPaq engine and DAX calculation speed.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 shrink-0">
          <div className="px-4 py-2.5 rounded-full bg-surface-container-lowest/80 backdrop-blur-md shadow-sm flex items-center gap-2.5">
            <Icon name="neurology" className={`text-secondary text-[18px] ${plan?.ai_status === "pending" ? "animate-pulse" : ""}`} />
            <div className="flex flex-col text-left">
              <span className="font-label-sm text-label-sm text-on-surface font-semibold">AI Data Modeler</span>
              <span className="font-code-sm text-code-sm text-on-surface-variant">
                {!plan ? "Loading…" : plan.ai_status === "pending" ? "Reviewing table roles…" : plan.ai_status === "done" ? "Schema Synthesis Active" : "Rule-based Modeler"}
              </span>
            </div>
          </div>
          {plan && (
            <div className={`px-4 py-2.5 rounded-full font-label-sm text-label-sm font-semibold tracking-wide flex items-center gap-2 shadow-sm ${plan.health_score >= 85 ? "bg-secondary-container text-primary" : "bg-error-container text-on-error-container"}`}>
              <Icon name={plan.health_score >= 85 ? "verified" : "report"} className="text-[16px]" />
              <span>HEALTH SCORE: {plan.health_score}% STAR SCHEMA {plan.health_score >= 85 ? "COMPLIANT" : "NEEDS FIXES"}</span>
            </div>
          )}
        </div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3 mb-5 px-1">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!plan || busy || auto}
            title={auto ? "Using the automatic star schema" : "Discard manual table and relationship changes"}
            onClick={() => update((s) => ({ ...s, table_overrides: {}, removed_relationships: [], added_relationships: [] }))}
            className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full font-label-sm text-label-sm font-semibold shadow-sm transition-transform active:scale-95 ${auto ? "bg-secondary-container text-primary" : "bg-surface-container-lowest/80 text-on-surface"}`}
          >
            <Icon name="stars" className="text-[16px]" />
            <span>{auto ? "Auto Star Schema" : "Reset to Auto Star Schema"}</span>
          </button>
          <button
            type="button"
            aria-pressed={plan?.settings.hide_keys ?? true}
            disabled={!plan || busy}
            onClick={() => update((s) => ({ ...s, hide_keys: !s.hide_keys }))}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-surface-container-lowest/80 backdrop-blur-md text-on-surface font-label-sm text-label-sm font-medium hover:bg-surface-container-lowest transition-all"
          >
            <Icon name={plan?.settings.hide_keys === false ? "visibility" : "visibility_off"} className="text-[16px] text-pine" />
            <span>{plan?.settings.hide_keys === false ? "Show Foreign/Surrogate Keys" : "Hide Foreign/Surrogate Keys"}</span>
          </button>
          <button
            type="button"
            aria-pressed={showFilters}
            onClick={() => setShowFilters((v) => !v)}
            className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full font-label-sm text-label-sm transition-all ${showFilters ? "bg-surface-container-lowest text-on-surface shadow-sm" : "bg-surface-container-lowest/50 text-on-surface-variant hover:text-on-surface"}`}
          >
            <Icon name="sync_alt" className="text-[16px]" />
            <span>Show Filter Directions</span>
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="hidden sm:flex items-center gap-3 px-3.5 py-1 rounded-full bg-surface-container-lowest/60 backdrop-blur-md font-label-sm text-label-sm text-on-surface-variant">
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-primary-container" />Fact (Central)</span>
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-surface-container-lowest shadow-sm" />Dimension</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-secondary-container" />Active 1:*</span>
          </div>
          <div className="flex items-center gap-1 p-1 rounded-full bg-surface-container-lowest/80 backdrop-blur-md shadow-sm">
            <button type="button" aria-label="Zoom out" onClick={() => step(-1)} className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:text-on-surface hover:bg-surface-container">
              <Icon name="remove" className="text-[16px]" />
            </button>
            <span className="font-code-sm text-code-sm px-2 text-on-surface font-medium select-none">{Math.round(zoom * 100)}%</span>
            <button type="button" aria-label="Zoom in" onClick={() => step(1)} className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:text-on-surface hover:bg-surface-container">
              <Icon name="add" className="text-[16px]" />
            </button>
            <span className="w-px h-4 bg-outline-variant/30 mx-1" />
            <button type="button" onClick={fit} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-on-surface-variant hover:text-on-surface font-label-sm text-label-sm hover:bg-surface-container">
              <Icon name="fit_screen" className="text-[15px]" />
              <span>Fit</span>
            </button>
            <button type="button" onClick={() => setZoom(1)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-on-surface-variant hover:text-on-surface font-label-sm text-label-sm hover:bg-surface-container">
              <Icon name="account_tree" className="text-[15px]" />
              <span>100%</span>
            </button>
          </div>
        </div>
      </section>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-8 flex flex-col gap-4">
          <div className="relative w-full rounded-card bg-surface-container-lowest/75 backdrop-blur-[16px] shadow-card p-6 sm:p-8 min-h-[640px] overflow-hidden">
            <div className="absolute inset-0 pointer-events-none opacity-40 [background-image:radial-gradient(#C4C7C7_1px,transparent_1px)] [background-size:20px_20px]" />
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 rounded-full bg-secondary-container/10 blur-3xl pointer-events-none" />
            <div ref={frame} className={`relative overflow-x-auto transition-opacity ${busy ? "opacity-60" : ""}`}>
              {plan ? (
                <SchemaDiagram
                  plan={plan}
                  zoom={zoom}
                  showFilters={showFilters}
                  onToggleKind={(table, kind) => override(table, { kind })}
                  onExclude={(table) => override(table, { included: false })}
                />
              ) : (
                !error && <div className="h-[560px] rounded-panel bg-hatched animate-pulse" />
              )}
            </div>
          </div>

          {excluded.length > 0 && (
            <div className="rounded-panel bg-surface-container-lowest/70 backdrop-blur-md p-4 flex flex-col gap-2.5">
              <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-semibold px-1">Excluded from model</span>
              <div className="flex flex-wrap gap-2">
                {excluded.map((t) => (
                  <span key={t.name} title={t.exclusion_reason ?? undefined} className="inline-flex items-center gap-2 pl-3 pr-1 py-1 rounded-full bg-surface-container-low font-code-sm text-code-sm text-on-surface-variant">
                    {t.name}
                    <span className="text-[10px] text-outline">{t.exclusion_reason}</span>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => override(t.name, { included: true })}
                      className="px-2.5 py-0.5 rounded-full bg-surface-container-lowest text-on-surface font-label-sm text-label-sm hover:bg-secondary-container/40"
                    >
                      Include
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-4">
          {plan && (
            <ModelSidePanel
              plan={plan}
              busy={busy}
              onFiscalMonth={(m) => update((s) => ({ ...s, fiscal_year_start_month: m }))}
              onDateTable={(enabled) => update((s) => ({ ...s, date_table: enabled }))}
              onAddRelationship={(r) => update((s) => ({ ...s, added_relationships: [...s.added_relationships, r] }))}
              onRemoveRelationship={removeRelationship}
              onValidate={validate}
            />
          )}
        </div>
      </div>

      <div className="sticky bottom-6 mt-10 z-40 w-full max-w-5xl mx-auto px-4">
        <div className="p-3 px-6 rounded-panel md:rounded-full bg-surface-container-lowest/90 backdrop-blur-xl shadow-[0_16px_40px_-8px_rgba(35,35,35,0.18)] flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className={`w-2.5 h-2.5 rounded-full ${problems ? "bg-coral" : "bg-pine"}`} />
            <span className="font-label-md text-label-md text-on-surface font-medium">
              Step 4 of 9 • {!plan ? "Building model…" : problems ? `${problems} model ${problems === 1 ? "issue" : "issues"} to review` : "Star Schema validated • VertiPaq ready"}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href={`/project/context?project=${projectId}`}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md transition-all"
            >
              ← Back: Business Context
            </Link>
            <a
              href={tmdlZipUrl(projectId)}
              aria-disabled={!plan?.tmdl_valid}
              className={`hidden sm:inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md transition-all ${plan?.tmdl_valid ? "" : "pointer-events-none opacity-50"}`}
            >
              <Icon name="file_download" className="text-[16px]" />
              <span>Export Model TMDL</span>
            </a>
          </div>
          <PillButton href={`/project/kpis?project=${projectId}`} arrow>
            Next: KPIs &amp; DAX Measures
          </PillButton>
        </div>
      </div>
    </div>
  );
}
