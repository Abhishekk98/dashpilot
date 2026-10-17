"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import {
  type BusinessContext,
  type ContextSuggestion,
  deleteLogo,
  fetchHealth,
  getContext,
  getProject,
  logoUrl,
  polishGoals,
  type Project,
  saveContext,
  suggestContext,
  suggestPalette,
  uploadLogo,
} from "@/lib/api";

import { ArchetypeGrid } from "./ArchetypeGrid";
import { BrandKitCard } from "./BrandKitCard";
import { ContextActionBar, type SaveState } from "./ContextActionBar";
import { OrganizationCard } from "./OrganizationCard";

const AUTOSAVE_MS = 900;

function DomainScore({ score }: { score: number | null }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 rounded-full bg-primary-container text-on-primary shadow-[0_8px_24px_-4px_rgba(35,35,35,0.18)]">
      <div className="relative w-8 h-8 flex items-center justify-center">
        <svg className="w-8 h-8 -rotate-90" viewBox="0 0 36 36" aria-hidden="true">
          <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#474746" strokeWidth="3" />
          <circle
            cx="18" cy="18" r="15.9155" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"
            strokeDasharray={`${score ?? 0}, 100`} className="text-secondary-container"
          />
        </svg>
        <span className="absolute font-headline-md text-[11px] font-semibold text-secondary-container">{score ?? "–"}</span>
      </div>
      <div className="flex flex-col">
        <span className="font-label-sm text-label-sm uppercase tracking-wider text-secondary-container font-semibold">Semantic Match</span>
        <span className="font-body-md text-body-md font-medium text-on-primary leading-tight">
          Domain Score: {score === null ? "not set" : `${score}%`}
        </span>
      </div>
    </div>
  );
}

/** Step 3 screen state: the project's business context, auto-saved, plus the AI helpers. */
export function ContextWorkspace() {
  const router = useRouter();
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [context, setContext] = useState<BusinessContext | null>(null);
  const [aiOnline, setAiOnline] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [lastSaveMs, setLastSaveMs] = useState<number | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestNote, setSuggestNote] = useState<string | null>(null);
  const [palettePending, setPalettePending] = useState(false);
  const [paletteNote, setPaletteNote] = useState<string | null>(null);
  const [polishing, setPolishing] = useState(false);
  const [polishNote, setPolishNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef<BusinessContext | null>(null);

  useEffect(() => {
    latest.current = context;
  }, [context]);

  const change = useCallback((patch: Partial<BusinessContext>) => {
    setContext((c) => (c ? { ...c, ...patch } : c));
    setSaveState("dirty");
  }, []);

  /** Apply data-based suggestions; `force` replaces the chips (manual re-run), otherwise only empty fields are filled. */
  const applySuggestion = useCallback(
    (s: ContextSuggestion, force: boolean) => {
      const c = latest.current;
      if (!c) return;
      change({
        industries: force || c.industries.length === 0 ? s.industries : c.industries,
        audiences: force || c.audiences.length === 0 ? s.audiences : c.audiences,
        goals: c.goals.trim() ? c.goals : s.goals,
        domain_score: s.domain_score,
      });
      setSuggestNote(s.source === "ai" ? null : (s.note ?? "Rule-based suggestion from column names"));
    },
    [change],
  );

  const runSuggest = useCallback(
    async (id: string, force: boolean) => {
      setSuggesting(true);
      try {
        applySuggestion(await suggestContext(id), force);
      } catch (e) {
        setSuggestNote((e as Error).message);
      } finally {
        setSuggesting(false);
      }
    },
    [applySuggestion],
  );

  useEffect(() => {
    fetchHealth()
      .then((h) => setAiOnline(h.llm_configured))
      .catch(() => setAiOnline(false));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([getProject(projectId), getContext(projectId)])
      .then(([p, c]) => {
        setProject(p);
        setContext(c);
        latest.current = c;
        // First visit: pre-fill industry, audience and goals from the profiled data.
        if (c.updated_at === null && p.files.length > 0) void runSuggest(projectId, false);
      })
      .catch((e) => setError((e as Error).message || "Could not load the business context. Is the backend running?"));
  }, [projectId, runSuggest]);

  const save = useCallback(async () => {
    const current = latest.current;
    if (!projectId || !current) return;
    setSaveState("saving");
    const started = performance.now();
    try {
      const saved = await saveContext(projectId, current);
      // Keep edits typed while the request was in flight; only take server-owned fields.
      setContext((c) => (c ? { ...c, updated_at: saved.updated_at, logo: saved.logo } : saved));
      setLastSaveMs(Math.round(performance.now() - started));
      setSaveState((s) => (s === "saving" ? "saved" : s));
      return true;
    } catch (e) {
      setError((e as Error).message);
      setSaveState("error");
      return false;
    }
  }, [projectId]);

  useEffect(() => {
    if (saveState !== "dirty") return;
    const timer = setTimeout(() => void save(), AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [context, saveState, save]);

  if (!projectId) {
    return (
      <div className="flex flex-col w-full">
        <StepHeader step={3} title="Business Context" />
        <PlaceholderCard
          icon="upload_file"
          title="No project selected"
          description="Upload and profile your data first; the business context is saved with the project."
        />
        <Link href="/project/upload" className="mt-6 self-center font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
          Go to Step 1: Upload
        </Link>
      </div>
    );
  }

  const handleLogo = async (file: File) => {
    setError(null);
    try {
      const updated = await uploadLogo(projectId, file);
      setContext((c) => (c ? { ...c, logo: updated.logo } : updated));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleRemoveLogo = async () => {
    try {
      await deleteLogo(projectId);
      setContext((c) => (c ? { ...c, logo: null } : c));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handlePalette = async () => {
    if (!context) return;
    setPalettePending(true);
    try {
      const s = await suggestPalette(projectId, context.palette.accent, Boolean(context.logo));
      change({ palette: s.palette });
      setPaletteNote(s.source === "ai" ? s.rationale : `Rule-based palette${s.note ? ` (AI unavailable: ${s.note})` : ""}. ${s.rationale}`);
    } catch (e) {
      setPaletteNote((e as Error).message);
    } finally {
      setPalettePending(false);
    }
  };

  const handlePolish = async () => {
    if (!context) return;
    setPolishing(true);
    try {
      const s = await polishGoals(projectId, context.goals);
      if (s.source === "ai") change({ goals: s.goals });
      setPolishNote(s.source === "ai" ? "Spec refined by AI Co-Analyst" : s.note);
    } catch (e) {
      setPolishNote((e as Error).message);
    } finally {
      setPolishing(false);
    }
  };

  const handleNext = async () => {
    if (saveState === "dirty" || saveState === "error" || context?.updated_at === null) {
      if (!(await save())) return;
    }
    router.push(`/project/model?project=${projectId}`);
  };

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={3} title={project?.name ?? "Business Context"} projectId={projectId} badge={project ? "Draft" : undefined} />

      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-8">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface-container-lowest/80 backdrop-blur-md shadow-sm">
            <span className="w-2 h-2 rounded-full bg-secondary-container" />
            <span className="font-code-sm text-code-sm tracking-wider uppercase text-on-surface-variant font-medium">
              Pipeline Phase III • Semantic Conditioning
            </span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface font-light tracking-tight">Define Business Context &amp; Brand Identity</h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-3xl">
            DashPilot tailors KPI calculations, DAX schema naming, visual weights, and reporting vocabulary to your organization&apos;s commercial domain.
          </p>
        </div>
        <div className="flex items-center flex-wrap gap-3">
          <button
            type="button"
            disabled={suggesting || !project?.files.length}
            onClick={() => runSuggest(projectId, true)}
            title={suggestNote ?? "Re-suggest industry, audience and goals from your data"}
            className="flex items-center gap-2.5 px-4 py-2 rounded-full bg-surface-container-lowest/80 backdrop-blur-md shadow-[0_8px_24px_-4px_rgba(35,35,35,0.06)] text-left hover:bg-surface-container-lowest transition-colors disabled:opacity-60"
          >
            <Icon name={suggesting ? "sync" : "psychology"} className={`text-[18px] text-secondary ${suggesting ? "animate-spin" : ""}`} />
            <span className="flex flex-col">
              <span className="font-label-sm text-label-sm text-on-surface font-semibold leading-tight">AI Co-Analyst</span>
              <span className="font-code-sm text-[10px] text-on-surface-variant leading-none">
                {suggesting ? "Reading your columns…" : aiOnline && !suggestNote ? "Context Synthesis Online" : "Rule-based Suggestions"}
              </span>
            </span>
          </button>
          <DomainScore score={context?.domain_score ?? null} />
        </div>
      </section>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}

      {!context ? (
        <div className="h-96 rounded-card bg-hatched animate-pulse mb-10" />
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-7 mb-10">
            <div className="lg:col-span-7 flex flex-col gap-6">
              <OrganizationCard context={context} onChange={change} onPolish={handlePolish} polishing={polishing} polishNote={polishNote} />
            </div>
            <div className="lg:col-span-5 flex flex-col gap-6">
              <BrandKitCard
                context={context}
                logoSrc={context.logo ? logoUrl(projectId, context.logo.uploaded_at) : null}
                onChange={change}
                onLogo={handleLogo}
                onRemoveLogo={handleRemoveLogo}
                onSuggestPalette={handlePalette}
                suggesting={palettePending}
                paletteNote={paletteNote}
              />
            </div>
          </div>
          <ArchetypeGrid value={context.archetype} onChange={(archetype) => change({ archetype })} />
        </>
      )}

      <ContextActionBar
        state={saveState}
        lastSaveMs={lastSaveMs}
        everSaved={Boolean(context?.updated_at)}
        backHref={`/project/clean?project=${projectId}`}
        onSave={() => void save()}
        onNext={handleNext}
      />
    </div>
  );
}
