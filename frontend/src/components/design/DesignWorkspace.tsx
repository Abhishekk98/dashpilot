"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PillTag } from "@/components/ui/PillTag";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import {
  type DashboardPlan,
  type DesignVariant,
  generateDesigns,
  getDashboardPlan,
  getProject,
  type PlanResponse,
  type Project,
  regeneratePlan,
  saveDashboardPlan,
  selectDesign,
  type VisualInput,
} from "@/lib/api";

import { OptionAPanel } from "./OptionAPanel";
import { OptionCPanel } from "./OptionCPanel";
import { PlanWireframe } from "./PlanWireframe";
import { DesignFrame, ScaledCanvas } from "./ScaledCanvas";
import { type Draft, VisualEditor } from "./VisualEditor";

type Method = "A" | "B" | "C";

const METHODS: { key: Method; icon: string; title: string; text: string; available: boolean }[] = [
  { key: "B", icon: "auto_awesome", title: "Design with DashPilot (AI)", text: "Three styled 1280×720 designs from your plan and brand, each checked against the design contract.", available: true },
  { key: "C", icon: "image_search", title: "Design from Reference Image", text: "Upload a dashboard you like; DashPilot takes its style (not its layout) and designs your KPIs in it.", available: true },
  { key: "A", icon: "draw", title: "Design with Google Stitch", text: "Copy a ready-made Stitch prompt, design in Stitch and upload the export; Power BI gets exactly that design.", available: true },
];

const LIMITS = { kpi: 5, chart: 6, slicer: 3 } as const;

function toDrafts(plan: DashboardPlan): Draft[] {
  return plan.visuals.map((v) => ({
    key: v.id,
    role: v.role,
    type: v.type,
    title: v.title,
    measures: v.measures,
    dimension: v.dimension,
    sort: v.sort,
    purpose: v.purpose,
    question_id: v.question_id,
    text: v.text,
  }));
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars -- drop the React key
const strip = (drafts: Draft[]): VisualInput[] => drafts.map(({ key, ...rest }) => rest);

/** Step 7 screen: dashboard plan editor (wireframe + visual list) and design method B variants. */
export function DesignWorkspace() {
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [data, setData] = useState<PlanResponse | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [title, setTitle] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "save" | "rebuild" | "ai" | "design" | "select">(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<DesignVariant | null>(null);
  const [method, setMethod] = useState<Method>("B");

  const load = useCallback((res: PlanResponse) => {
    setData((prev) => {
      if (!prev && res.design.selected_method) setMethod(res.design.selected_method); // reopen on the method in use
      return res;
    });
    setDrafts(toDrafts(res.plan));
    setTitle(res.plan.title);
    if (res.notes.length) setNotes(res.notes);
  }, []);

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    Promise.all([getProject(projectId), getDashboardPlan(projectId)])
      .then(([p, res]) => {
        if (!alive) return;
        setProject(p);
        load(res);
      })
      .catch((e) => alive && setError((e as Error).message || "Could not build the dashboard plan. Is the backend running?"));
    return () => {
      alive = false;
    };
  }, [projectId, load]);

  useEffect(() => {
    if (!preview) return;
    const close = (e: KeyboardEvent) => e.key === "Escape" && setPreview(null);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [preview]);

  const plan = data?.plan ?? null;
  const design = data?.design ?? null;
  const dirty = useMemo(
    () => !!plan && (title !== plan.title || JSON.stringify(strip(drafts)) !== JSON.stringify(strip(toDrafts(plan)))),
    [plan, drafts, title],
  );

  if (!projectId) {
    return (
      <div className="flex flex-col w-full">
        <StepHeader step={7} title="Choose Design Method" />
        <PlaceholderCard icon="upload_file" title="No project selected" description="Upload data, build measures and insights first; the dashboard plan is made from them." />
        <Link href="/project/upload" className="mt-6 self-center font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
          Go to Step 1: Upload
        </Link>
      </div>
    );
  }

  const run = async (kind: NonNullable<typeof busy>, action: () => Promise<PlanResponse>) => {
    setBusy(kind);
    setError(null);
    setNotes([]);
    try {
      load(await action());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const count = (role: Draft["role"]) => drafts.filter((d) => d.role === role).length;

  const add = (role: "kpi" | "chart" | "slicer") => {
    if (!plan) return;
    const usedMeasures = new Set(drafts.flatMap((d) => d.measures));
    const usedDims = new Set(drafts.map((d) => d.dimension));
    const titles = new Set(drafts.map((d) => d.title.toLowerCase()));
    const measure = plan.measures.find((m) => !usedMeasures.has(m)) ?? plan.measures[0] ?? "";
    const dim = plan.dimensions.find((d) => d.kind !== "date" && !usedDims.has(d.field)) ?? plan.dimensions.find((d) => d.kind !== "date") ?? plan.dimensions[0];
    let draft: Draft;
    if (role === "kpi") {
      draft = { key: `new-${Date.now()}`, role, type: "card", title: measure, measures: [measure], dimension: null, sort: null, purpose: `Headline value of ${measure}.`, question_id: null, text: [] };
    } else if (role === "slicer") {
      draft = { key: `new-${Date.now()}`, role, type: "slicer", title: dim ? dim.label.replace(/\b\w/g, (c) => c.toUpperCase()) : "Filter", measures: [], dimension: dim?.field ?? null, sort: null, purpose: "", question_id: null, text: [] };
    } else {
      const base = `${plan.measures[0] ?? "Value"} by ${dim ? dim.label.replace(/\b\w/g, (c) => c.toUpperCase()) : "Category"}`;
      let name = base;
      for (let n = 2; titles.has(name.toLowerCase()); n++) name = `${base} (${n})`;
      draft = { key: `new-${Date.now()}`, role, type: "clustered_column", title: name, measures: plan.measures.slice(0, 1), dimension: dim?.field ?? null, sort: "desc", purpose: "", question_id: null, text: [] };
    }
    // Insert after the last visual of the same role so the layout groups stay together.
    const last = drafts.map((d) => d.role).lastIndexOf(role);
    const at = last >= 0 ? last + 1 : role === "slicer" ? 0 : role === "kpi" ? drafts.filter((d) => d.role === "slicer").length : drafts.findIndex((d) => d.role === "insights");
    const next = [...drafts];
    next.splice(at < 0 ? next.length : at, 0, draft);
    setDrafts(next);
    setSelected(draft.key);
  };

  const exportPlan = () => {
    if (!plan) return;
    const blob = new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(project?.name ?? "dashboard").replace(/[^\w-]+/g, "_")}_plan.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const charts = plan?.visuals.filter((v) => v.role === "chart").length ?? 0;
  const kpis = plan?.visuals.filter((v) => v.role === "kpi").length ?? 0;
  const chosenLabel = design?.selected ? (design.selected_label ?? design.variants.find((v) => v.id === design.selected)?.label ?? null) : null;
  const canContinue = !!chosenLabel && !design?.selected_stale;

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={7} title={project?.name ?? "Choose Design Method"} projectId={projectId} badge={project ? "Draft" : undefined} />

      <section className="space-y-2 mb-8">
        <span className="inline-flex items-center gap-2 w-fit px-3 py-1 rounded-full bg-surface-container-lowest/80 font-code-sm text-code-sm uppercase tracking-wider text-on-surface-variant">
          <span className="w-2 h-2 rounded-full bg-secondary-container" /> Dashboard Planner • 1280×720 single page
        </span>
        <h1 className="font-headline-xl text-headline-xl text-on-surface font-light tracking-tight">Plan your dashboard, then pick a design</h1>
        <p className="font-body-lg text-body-lg text-on-surface-variant max-w-3xl">
          Every visual answers a business question and uses only validated measures. Edit the plan, then generate designs that keep exactly this layout.
        </p>
      </section>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}
      {notes.length > 0 && (
        <div role="status" className="mb-6 p-4 rounded-inner bg-surface-container-lowest/80 shadow-card flex flex-col gap-1.5">
          {notes.map((n) => (
            <p key={n} className="flex items-start gap-2 font-body-md text-xs text-on-surface">
              <Icon name="info" className="text-[16px] text-secondary shrink-0" />
              <span>{n}</span>
            </p>
          ))}
        </div>
      )}

      {!plan && !error && <div className="h-96 rounded-card bg-hatched animate-pulse mb-8" />}

      {plan && (
        <>
          {/* --- Part 1: plan ------------------------------------------------------------ */}
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start mb-10">
            <div className="xl:col-span-7 flex flex-col gap-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight flex items-center gap-2">
                  <Icon name="dashboard" className="text-[22px]" /> Dashboard Plan
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                  <PillTag tone={plan.valid ? "success" : "error"} dot size="md">
                    {plan.valid ? "Plan valid" : `${plan.issues.length} issue${plan.issues.length === 1 ? "" : "s"}`}
                  </PillTag>
                  <PillTag size="md">{plan.source === "ai" ? "AI-polished titles" : "Rule-based"}{plan.edited ? " · edited" : ""}</PillTag>
                </div>
              </div>
              <PlanWireframe plan={plan} highlight={selected} onPick={(id) => setSelected(id)} />
              {dirty && (
                <p className="font-body-md text-xs text-on-surface-variant flex items-center gap-1.5">
                  <Icon name="info" className="text-[14px]" /> The wireframe updates when you save your changes.
                </p>
              )}
              {!plan.valid && (
                <ul className="p-4 rounded-inner bg-error-container/40 text-on-error-container flex flex-col gap-1">
                  {plan.issues.map((i) => (
                    <li key={i} className="flex items-start gap-2 font-body-md text-xs">
                      <Icon name="warning" className="text-[14px] shrink-0 mt-0.5" /> {i}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="xl:col-span-5 flex flex-col gap-4">
              <label className="flex flex-col gap-1">
                <span className="font-label-sm text-label-sm text-on-surface-variant">Dashboard title</span>
                <input
                  value={title}
                  maxLength={80}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-2xl bg-surface-container-lowest/90 shadow-card text-on-surface font-body-md text-body-md outline-none focus:ring-2 focus:ring-secondary-container"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                {(["kpi", "chart", "slicer"] as const).map((r) => (
                  <button
                    key={r}
                    type="button"
                    disabled={count(r) >= LIMITS[r]}
                    onClick={() => add(r)}
                    className="px-3.5 py-1.5 rounded-full bg-surface-container-lowest/80 text-on-surface font-label-sm text-label-sm flex items-center gap-1.5 hover:bg-surface-container disabled:opacity-40"
                  >
                    <Icon name="add" className="text-[14px]" /> {r === "kpi" ? "KPI card" : r === "chart" ? "Chart" : "Slicer"}
                  </button>
                ))}
              </div>
              <div className="max-h-[560px] overflow-y-auto pr-1 -mr-1">
                <VisualEditor plan={plan} drafts={drafts} selected={selected} onSelect={(k) => setSelected(k || null)} onChange={setDrafts} />
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                <PillButton icon={busy === "save" ? "sync" : "save"} disabled={!dirty || busy !== null} onClick={() => run("save", () => saveDashboardPlan(projectId, strip(drafts), title))}>
                  Save &amp; re-layout
                </PillButton>
                {dirty && (
                  <button type="button" onClick={() => load({ ...data!, notes: [] })} className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface underline underline-offset-4">
                    Discard changes
                  </button>
                )}
                <div className="flex items-center gap-2 ml-auto">
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => run("rebuild", () => regeneratePlan(projectId, false))}
                    title="Rebuild the plan from your measures and pinned insights (drops your edits)"
                    className="px-3.5 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface font-label-sm text-label-sm flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <Icon name={busy === "rebuild" ? "sync" : "restart_alt"} className={`text-[14px] ${busy === "rebuild" ? "animate-spin" : ""}`} /> Rebuild
                  </button>
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => run("ai", () => regeneratePlan(projectId, true))}
                    title="Rebuild and let AI polish chart titles and purposes (numbers and layout stay rule-based)"
                    className="px-3.5 py-2 rounded-full bg-secondary-container/50 text-on-surface font-label-sm text-label-sm flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <Icon name={busy === "ai" ? "sync" : "auto_awesome"} className={`text-[14px] ${busy === "ai" ? "animate-spin" : ""}`} /> Refine titles with AI
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* --- Part 2: design method --------------------------------------------------- */}
          <section className="flex flex-col gap-5 mb-10">
            <h2 className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight flex items-center gap-2">
              <Icon name="palette" className="text-[22px]" /> Design Method
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {METHODS.map((m) => {
                const active = m.key === method;
                return (
                  <button
                    key={m.key}
                    type="button"
                    disabled={!m.available}
                    aria-pressed={active}
                    onClick={() => m.available && setMethod(m.key as Method)}
                    className={`p-5 rounded-card flex flex-col gap-3 text-left transition-shadow ${active ? "bg-surface-container-lowest/95 shadow-card ring-2 ring-primary-container" : m.available ? "bg-surface-container-lowest/80 hover:shadow-card" : "bg-surface-container-lowest/60 opacity-70 cursor-not-allowed"}`}
                  >
                    <div className="flex items-center justify-between gap-2 w-full">
                      <span className="w-10 h-10 rounded-full bg-secondary-container/40 flex items-center justify-center">
                        <Icon name={m.icon} className="text-[20px] text-on-surface" />
                      </span>
                      {active ? (
                        <PillTag tone="dark" dot size="md">Selected</PillTag>
                      ) : m.available ? (
                        <PillTag size="md">Available</PillTag>
                      ) : (
                        <PillTag tone="warning" size="md">Coming soon</PillTag>
                      )}
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="font-code-sm text-code-sm text-on-surface-variant">Option {m.key}</span>
                      <span className="font-title-lg text-title-lg text-on-surface font-semibold">{m.title}</span>
                      <span className="font-body-md text-xs text-on-surface-variant leading-relaxed">{m.text}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            {method === "A" && (
              <OptionAPanel
                projectId={projectId}
                visuals={plan.visuals}
                design={design}
                blocked={dirty ? "Save your plan changes first" : !plan.valid ? "Fix the plan issues first" : null}
                selecting={busy === "select"}
                onSelect={() => run("select", () => selectDesign(projectId, "stitch"))}
              />
            )}

            {method === "C" && (
              <OptionCPanel
                projectId={projectId}
                design={design}
                blocked={dirty ? "Save your plan changes first" : !plan.valid ? "Fix the plan issues first" : null}
                selecting={busy === "select"}
                onSelect={(id) => run("select", () => selectDesign(projectId, id))}
                onPreview={setPreview}
              />
            )}

            {method === "B" && (
            <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="font-body-md text-body-md text-on-surface-variant max-w-2xl">
                {design?.variants.length
                  ? design.stale
                    ? "The plan changed after these designs were made. Regenerate so the designs match the plan."
                    : "Pick the design to build in Power BI. Chart areas stay empty; Power BI draws the real visuals there."
                  : "Generate three styles of the same plan: Dark Futuristic, Light Elegant and Glassmorphism."}
              </p>
              <PillButton
                variant="accent"
                icon={busy === "design" ? "sync" : "auto_awesome"}
                disabled={busy !== null || dirty || !plan.valid}
                title={dirty ? "Save your plan changes first" : !plan.valid ? "Fix the plan issues first" : undefined}
                onClick={() => run("design", () => generateDesigns(projectId))}
              >
                {busy === "design" ? "Designing…" : design?.variants.length ? "Regenerate 3 designs" : "Generate 3 designs"}
              </PillButton>
            </div>

            {busy === "design" && (
              <p className="font-body-md text-xs text-on-surface-variant flex items-center gap-1.5">
                <Icon name="hourglass_top" className="text-[14px]" /> AI designs each style and checks it against the contract; this can take 1–3 minutes. Built-in templates fill in if AI is unavailable.
              </p>
            )}
            {busy === "design" && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                {[0, 1, 2].map((n) => (
                  <div key={n} className="aspect-video rounded-card bg-hatched animate-pulse" />
                ))}
              </div>
            )}

            {busy !== "design" && design && design.variants.length > 0 && (
              <div className={`grid grid-cols-1 lg:grid-cols-3 gap-5 ${design.stale ? "opacity-60" : ""}`}>
                {design.variants.map((v) => {
                  const isChosen = design.selected === v.id;
                  return (
                    <div key={v.id} className={`p-3 rounded-card bg-surface-container-lowest/90 shadow-card flex flex-col gap-3 ${isChosen ? "ring-2 ring-primary-container" : ""}`}>
                      <button type="button" onClick={() => setPreview(v)} className="block rounded-inner overflow-hidden" aria-label={`Open ${v.label} full size`}>
                        <ScaledCanvas>
                          <DesignFrame html={v.html} title={v.label} />
                        </ScaledCanvas>
                      </button>
                      <div className="flex items-center justify-between gap-2 px-1">
                        <div className="flex flex-col min-w-0">
                          <span className="font-title-lg text-[15px] text-on-surface font-semibold">{v.label}</span>
                          <span className="font-body-md text-[11px] text-on-surface-variant truncate" title={v.note ?? undefined}>
                            {v.note ?? (v.source === "ai" ? `AI design, passed the contract${v.attempts > 1 ? ` on try ${v.attempts}` : ""}` : "Built-in template")}
                          </span>
                        </div>
                        <PillTag tone={v.source === "ai" ? "accent" : "neutral"} size="md">{v.source === "ai" ? "AI" : "Template"}</PillTag>
                      </div>
                      <div className="flex items-center gap-2 px-1 pb-1">
                        <PillButton
                          variant={isChosen ? "primary" : "secondary"}
                          icon={isChosen ? "check_circle" : "radio_button_unchecked"}
                          disabled={busy !== null || design.stale}
                          onClick={() => run("select", () => selectDesign(projectId, v.id))}
                        >
                          {isChosen ? "Selected" : "Use this design"}
                        </PillButton>
                        <button type="button" onClick={() => setPreview(v)} className="ml-auto font-label-sm text-label-sm text-on-surface-variant hover:text-on-surface flex items-center gap-1">
                          <Icon name="open_in_full" className="text-[14px]" /> Full size
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            </>
            )}
          </section>
        </>
      )}

      {preview && (
        <div role="dialog" aria-modal="true" aria-label={`${preview.label} preview`} className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6" onClick={() => setPreview(null)}>
          <div className="w-full max-w-[1280px] flex flex-col gap-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between text-white">
              <span className="font-title-lg text-title-lg font-semibold">{preview.label} · 1280×720</span>
              <button type="button" aria-label="Close" onClick={() => setPreview(null)} className="w-9 h-9 rounded-full bg-white/15 flex items-center justify-center">
                <Icon name="close" className="text-[20px]" />
              </button>
            </div>
            <ScaledCanvas className="rounded-inner">
              <DesignFrame html={preview.html} title={preview.label} />
            </ScaledCanvas>
          </div>
        </div>
      )}

      <div className="sticky bottom-4 z-40 w-full">
        <div className="p-4 md:px-7 rounded-panel md:rounded-full bg-surface-container-lowest/90 backdrop-blur-xl shadow-[0_16px_40px_-8px_rgba(35,35,35,0.18)] flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-secondary-container" />
            <span className="font-label-md text-label-md text-on-surface">
              <strong className="font-semibold">Step 7 of 9</strong>
              {plan ? ` • ${kpis} KPI cards • ${charts} charts • ${chosenLabel ? `Design: ${chosenLabel}` : "No design selected"}` : " • Planning…"}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 justify-end">
            <Link
              href={`/project/insights?project=${projectId}`}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md flex items-center gap-1.5"
            >
              <Icon name="arrow_back" className="text-[16px]" /> Back: AI Insights
            </Link>
            <button
              type="button"
              disabled={!plan}
              onClick={exportPlan}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md flex items-center gap-1.5 disabled:opacity-50"
            >
              <Icon name="file_download" className="text-[16px]" /> Export Plan (.json)
            </button>
            {canContinue ? (
              <PillButton href={`/project/design-import?project=${projectId}`} arrow>
                Next: Design Import
              </PillButton>
            ) : (
              <PillButton arrow disabled title={chosenLabel ? "The plan or style changed; regenerate and select a design" : "Select a design first"}>
                Next: Design Import
              </PillButton>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
