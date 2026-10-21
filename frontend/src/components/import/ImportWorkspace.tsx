"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FidelityReport } from "@/components/design/FidelityReport";
import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import {
  designBackgroundUrl,
  designOriginalUrl,
  designThemeUrl,
  getDesignImport,
  getProject,
  type ImportResponse,
  importSelectedDesign,
  type MappingEdit,
  type Project,
  saveDesignMapping,
  setFidelityOverride,
  uploadDesignHtml,
} from "@/lib/api";

import { MappingCanvas } from "./MappingCanvas";
import { MappingPanel } from "./MappingPanel";

const ROLE_LABEL: Record<string, string> = { canvas: "Canvas", card: "Cards", text: "Text", muted: "Muted", accent: "Accent", other: "Accent 2" };

const toEdits = (res: ImportResponse): MappingEdit[] => res.design.mapping.map(({ visual_id, box_id, x, y, w, h }) => ({ visual_id, box_id, x, y, w, h }));

/** Client-side copy of the server's mapping rules, so problems show while editing. */
function localProblems(res: ImportResponse, mapping: MappingEdit[]): Set<string> {
  const bad = new Set<string>();
  const placed = mapping.filter((m) => m.w > 0 && m.h > 0);
  const boxOwner = new Map<string, string>();
  for (const v of res.visuals) if (!placed.some((m) => m.visual_id === v.id)) bad.add(v.id);
  for (const m of placed) {
    if (m.box_id) {
      if (boxOwner.has(m.box_id)) {
        bad.add(m.visual_id);
        bad.add(boxOwner.get(m.box_id) as string);
      }
      boxOwner.set(m.box_id, m.visual_id);
    }
    if (m.x < 0 || m.y < 0 || m.x + m.w > 1280 || m.y + m.h > 720 || m.w < 40 || m.h < 30) bad.add(m.visual_id);
  }
  placed.forEach((a, i) =>
    placed.slice(i + 1).forEach((b) => {
      if (a.x + 1 < b.x + b.w && b.x + 1 < a.x + a.w && a.y + 1 < b.y + b.h && b.y + 1 < a.y + a.h) {
        bad.add(a.visual_id);
        bad.add(b.visual_id);
      }
    }),
  );
  return bad;
}

/** Step 8 screen: design import (Option B design or uploaded HTML), mapping editor, background and theme. */
export function ImportWorkspace() {
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [data, setData] = useState<ImportResponse | null>(null);
  const [mapping, setMapping] = useState<MappingEdit[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<"background" | "original">("background");
  const [showBoxes, setShowBoxes] = useState(true);
  const [busy, setBusy] = useState<null | "load" | "save" | "upload" | "selected">("load");
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback((res: ImportResponse) => {
    setData(res);
    setMapping(toEdits(res));
    setNotes([...res.notes, ...res.design.notes].filter((n, i, all) => all.indexOf(n) === i));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    getProject(projectId).then((p) => alive && setProject(p)).catch(() => undefined);
    getDesignImport(projectId)
      .then((res) => alive && load(res))
      .catch((e) => alive && setError((e as Error).message || "Could not import the design. Is the backend running?"))
      .finally(() => alive && setBusy(null));
    return () => {
      alive = false;
    };
  }, [projectId, load]);

  const dirty = useMemo(() => !!data && JSON.stringify(mapping) !== JSON.stringify(toEdits(data)), [data, mapping]);
  const problems = useMemo(() => {
    const bad = data ? localProblems(data, mapping) : new Set<string>();
    const f = data?.design.fidelity;
    // Cards that do not reproduce the design closely enough are flagged too (until the user accepts them).
    if (f && !f.passed && !data?.design.fidelity_override) f.cards.filter((c) => !c.passed && c.visual_id).forEach((c) => bad.add(c.visual_id as string));
    return bad;
  }, [data, mapping]);

  if (!projectId) {
    return (
      <div className="flex flex-col w-full">
        <StepHeader step={8} title="Import Design & Visual Mapping" />
        <PlaceholderCard icon="upload_file" title="No project selected" description="Plan the dashboard and pick a design in Step 7 first." />
        <Link href="/project/upload" className="mt-6 self-center font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
          Go to Step 1: Upload
        </Link>
      </div>
    );
  }

  const run = async (kind: NonNullable<typeof busy>, action: () => Promise<ImportResponse>) => {
    setBusy(kind);
    setError(null);
    try {
      load(await action());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const change = (visualId: string, patch: Partial<MappingEdit>) => setMapping((cur) => cur.map((m) => (m.visual_id === visualId ? { ...m, ...patch } : m)));

  // Picking a slot another visual uses swaps the two visuals' slots.
  const assign = (visualId: string, boxId: string) => {
    const box = data?.design.boxes.find((b) => b.id === boxId);
    if (!box) return;
    setMapping((cur) => {
      const mine = cur.find((m) => m.visual_id === visualId);
      return cur.map((m) => {
        if (m.visual_id === visualId) return { ...m, box_id: box.id, x: box.x, y: box.y, w: box.w, h: box.h };
        if (m.box_id === boxId && mine) return { ...m, box_id: mine.box_id, x: mine.x, y: mine.y, w: mine.w, h: mine.h };
        return m;
      });
    });
  };

  const panelChange = (visualId: string, patch: Partial<MappingEdit>) => {
    if (patch.box_id && patch.w) assign(visualId, patch.box_id);
    else change(visualId, patch);
  };

  const exportMapping = () => {
    if (!data) return;
    const titles = new Map(data.visuals.map((v) => [v.id, v]));
    const out = {
      canvas: { width: 1280, height: 720 },
      source: data.design.source_name,
      visuals: mapping.map((m) => ({ ...m, title: titles.get(m.visual_id)?.title, type: titles.get(m.visual_id)?.type, measures: titles.get(m.visual_id)?.measures })),
      theme: data.design.theme,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(project?.name ?? "dashboard").replace(/[^\w-]+/g, "_")}_mapping.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const d = data?.design;
  const placedCount = mapping.filter((m) => m.w > 0 && m.h > 0).length;
  const total = data?.visuals.length ?? 0;
  const autoMatched = d ? d.mapping.filter((m) => m.method !== "none").length : 0;
  const fidelityOk = !d?.fidelity || d.fidelity.passed || d.fidelity_override;
  const complete = !!d && d.valid && !dirty && fidelityOk && problems.size === 0;

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={8} title={project?.name ?? "Import Design"} projectId={projectId} badge={project ? "Draft" : undefined} />

      <header className="w-full mb-7 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
        <div className="flex flex-col gap-2 max-w-3xl">
          <span className="inline-flex items-center gap-2 self-start px-3 py-1 rounded-full bg-surface-container text-on-surface-variant font-code-sm text-code-sm tracking-wider uppercase">
            <span className="w-1.5 h-1.5 rounded-full bg-secondary-container" /> Canvas Ingestion Engine • DOM &amp; CSS Parser
          </span>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-light">Import Design &amp; Visual Slot Mapping</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            DashPilot renders your 1280×720 design, finds every card, extracts color tokens and binds each planned visual and its DAX measures to a slot.
          </p>
        </div>
        {d && (
          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <span className="px-3.5 py-1.5 rounded-full bg-surface-container-lowest shadow-sm flex items-center gap-2 text-on-surface-variant font-label-md text-label-md">
              <Icon name="aspect_ratio" className="text-[16px]" /> Target Canvas: <strong className="text-on-surface font-code-sm">1280 × 720</strong>
            </span>
            <span className="px-3.5 py-1.5 rounded-full bg-surface-container-lowest shadow-sm flex items-center gap-2 text-on-surface-variant font-label-md text-label-md">
              <span className="w-2 h-2 rounded-full bg-secondary-container" />
              {d.source === "upload" ? "Uploaded:" : "Source:"} <span className="font-code-sm text-on-surface">{d.source_name}</span>
              <Icon name="check" className="text-[16px] text-on-secondary-container" />
            </span>
            <span className="px-3.5 py-1.5 rounded-full bg-secondary-fixed/50 text-on-secondary-fixed flex items-center gap-1.5 font-label-sm text-label-sm uppercase tracking-wider font-semibold">
              <Icon name="auto_awesome" className="text-[15px]" /> {d.boxes.length} slots • {autoMatched}/{total} auto-matched
            </span>
          </div>
        )}
      </header>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">
            {error}{" "}
            {!data && (
              <Link href={`/project/design-method?project=${projectId}`} className="underline underline-offset-4">
                Go to Step 7
              </Link>
            )}
          </span>
        </div>
      )}
      {notes.length > 0 && (
        <div role="status" className="mb-6 p-4 rounded-inner bg-surface-container-lowest/80 shadow-card flex flex-col gap-1.5">
          {notes.map((n) => (
            <p key={n} className="flex items-start gap-2 font-body-md text-xs text-on-surface">
              <Icon name="info" className="text-[16px] text-secondary shrink-0" /> <span>{n}</span>
            </p>
          ))}
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        accept=".html,.htm,.zip,text/html,application/zip"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) void run("upload", () => uploadDesignHtml(projectId, f));
        }}
      />

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 w-full mb-6">
        <section className="xl:col-span-8 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3 px-1">
            <div className="flex items-center gap-2 p-1 rounded-full bg-surface-container shadow-inner">
              <span className="px-4 py-1.5 rounded-full bg-primary-container text-on-primary font-label-md text-label-md flex items-center gap-2 shadow-sm">
                <Icon name="code" className="text-[15px] text-secondary-container" /> HTML Export (Recommended) • DOM &amp; CSS
              </span>
              <span title="Image imports arrive with design method C" className="px-4 py-1.5 rounded-full text-on-surface-variant/60 font-label-md text-label-md flex items-center gap-1.5 cursor-not-allowed">
                <Icon name="image" className="text-[15px]" /> Image (PNG / Mockup) · soon
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => fileRef.current?.click()}
                className="flex items-center gap-1.5 font-label-md text-label-md text-on-surface-variant hover:text-on-surface px-3 py-1.5 rounded-full bg-surface-container-lowest/80 disabled:opacity-50"
              >
                <Icon name={busy === "upload" ? "sync" : "upload_file"} className={`text-[15px] ${busy === "upload" ? "animate-spin" : ""}`} /> Upload HTML / Stitch zip
              </button>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => run("selected", () => importSelectedDesign(projectId))}
                title="Import the design selected in Step 7 again (drops manual edits)"
                className="flex items-center gap-1.5 font-label-md text-label-md text-on-surface-variant hover:text-on-surface px-3 py-1.5 rounded-full bg-surface-container-lowest/80 disabled:opacity-50"
              >
                <Icon name="sync" className={`text-[15px] ${busy === "selected" ? "animate-spin" : ""}`} /> Re-import Step 7 design
              </button>
              <button
                type="button"
                onClick={() => setView(view === "background" ? "original" : "background")}
                className="flex items-center gap-1.5 font-label-md text-label-md text-on-surface-variant hover:text-on-surface px-3 py-1.5 rounded-full bg-surface-container-lowest/80"
              >
                <Icon name={view === "background" ? "wallpaper" : "web"} className="text-[15px]" /> {view === "background" ? "Clean background" : "Original design"}
              </button>
              <button
                type="button"
                onClick={() => setShowBoxes(!showBoxes)}
                className="flex items-center gap-2 font-label-md text-label-md text-on-surface px-3.5 py-1.5 rounded-full bg-surface-container-lowest shadow-sm"
              >
                <span className={`w-2 h-2 rounded-full bg-secondary-container ${showBoxes ? "" : "opacity-20"}`} /> Boundary Boxes
              </button>
            </div>
          </div>

          <div className="relative w-full rounded-[28px] bg-surface-container-lowest p-5 shadow-[0_12px_36px_-8px_rgba(35,35,35,0.06)]">
            {data && d ? (
              <div className={busy && busy !== "load" ? "opacity-60 pointer-events-none" : ""}>
                <MappingCanvas
                  view={view}
                  backgroundUrl={designBackgroundUrl(projectId, d.background_version)}
                  originalUrl={d.fidelity ? designOriginalUrl(projectId, d.background_version) : null}
                  html={data.html}
                  visuals={data.visuals}
                  mapping={mapping}
                  boxes={d.boxes}
                  showBoxes={showBoxes}
                  selected={selected}
                  problems={problems}
                  onSelect={setSelected}
                  onAssignBox={(boxId) => selected && assign(selected, boxId)}
                  onMove={change}
                />
              </div>
            ) : (
              <div className="aspect-video rounded-2xl bg-hatched animate-pulse flex items-center justify-center">
                {busy === "load" && <span className="font-label-md text-label-md text-on-surface-variant bg-surface-container-lowest/90 px-4 py-2 rounded-full">Rendering the design and detecting slots…</span>}
              </div>
            )}
          </div>

          {d && (
            <div className="w-full rounded-[24px] bg-surface-container-lowest p-5 shadow-sm flex flex-col lg:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="w-9 h-9 rounded-full bg-surface-container flex items-center justify-center text-on-surface">
                  <Icon name="palette" className="text-[20px]" />
                </span>
                <div>
                  <h3 className="font-title-lg text-title-lg font-medium text-on-surface">Extracted Theme Palette (from DOM &amp; CSS)</h3>
                  <span className="font-label-md text-label-md text-on-surface-variant">
                    {d.palette.length} colors • headings {d.heading_font} • numbers Segoe UI
                  </span>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                {d.palette.map((c) => (
                  <span key={`${c.role}-${c.hex}`} title={ROLE_LABEL[c.role]} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container font-code-sm text-code-sm">
                    <span className="w-3.5 h-3.5 rounded-full border border-surface-container-high" style={{ backgroundColor: c.hex }} />
                    <span className="text-on-surface font-medium">{c.hex}</span>
                    <span className="text-on-surface-variant">{ROLE_LABEL[c.role]}</span>
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="flex gap-0.5" title="Power BI data colors">
                  {d.theme.dataColors.map((c) => (
                    <span key={c} className="w-3 h-5 rounded-sm first:rounded-l-full last:rounded-r-full" style={{ backgroundColor: c }} />
                  ))}
                </span>
                <span className="px-3 py-1 rounded-full bg-secondary-fixed/50 text-on-secondary-fixed font-label-sm text-label-sm font-semibold flex items-center gap-1">
                  <Icon name="check" className="text-[14px]" /> PBIP Theme Ready
                </span>
                <a href={designThemeUrl(projectId)} className="px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-label-md flex items-center gap-1.5">
                  <Icon name="file_download" className="text-[16px]" /> JSON
                </a>
              </div>
            </div>
          )}
        </section>

        <aside className="xl:col-span-4 flex flex-col gap-4">
          <div className="rounded-[28px] bg-surface-container-lowest p-6 shadow-[0_12px_36px_-8px_rgba(35,35,35,0.06)] flex flex-col gap-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Icon name="hub" className="text-[20px] text-on-surface" />
                  <h2 className="font-headline-md text-headline-md font-semibold text-on-surface">Visual Mapping</h2>
                </div>
                <p className="font-body-md text-body-md text-on-surface-variant mt-1">Assign detected layout slots to your planned visuals and DAX measures.</p>
              </div>
              <span className="px-2.5 py-1 rounded-full bg-surface-container font-code-sm text-code-sm text-on-surface-variant font-medium shrink-0">
                {placedCount}/{total} placed
              </span>
            </div>

            {d?.fidelity && (
              <FidelityReport
                report={d.fidelity}
                override={d.fidelity_override}
                busy={busy !== null}
                onOverride={(v) => run("save", () => setFidelityOverride(projectId, v))}
              />
            )}

            {d && (dirty ? problems.size > 0 : d.issues.length > 0) && (
              <ul className="p-3 rounded-2xl bg-error-container/40 text-on-error-container flex flex-col gap-1">
                {(dirty ? [`${problems.size} visual${problems.size === 1 ? "" : "s"} need attention (highlighted in red).`] : d.issues).map((i) => (
                  <li key={i} className="flex items-start gap-1.5 font-body-md text-xs">
                    <Icon name="warning" className="text-[14px] shrink-0 mt-0.5" /> {i}
                  </li>
                ))}
              </ul>
            )}

            <div className="flex flex-col gap-3 max-h-[640px] overflow-y-auto pr-1">
              {data && d && (
                <MappingPanel
                  visuals={data.visuals}
                  mapping={mapping}
                  saved={d.mapping}
                  boxes={d.boxes}
                  selected={selected}
                  problems={problems}
                  onSelect={setSelected}
                  onChange={panelChange}
                />
              )}
            </div>
            {dirty && (
              <div className="flex items-center gap-3">
                <PillButton icon={busy === "save" ? "sync" : "save"} disabled={busy !== null} onClick={() => run("save", () => saveDesignMapping(projectId, mapping))}>
                  Save mapping
                </PillButton>
                <button type="button" onClick={() => data && setMapping(toEdits(data))} className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface underline underline-offset-4">
                  Discard
                </button>
              </div>
            )}
          </div>
        </aside>
      </div>

      <div className="sticky bottom-4 z-40 w-full">
        <div className="p-4 md:px-7 rounded-panel md:rounded-full bg-surface-container-lowest/90 backdrop-blur-xl shadow-[0_16px_40px_-8px_rgba(35,35,35,0.18)] flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className={`w-2.5 h-2.5 rounded-full ${complete ? "bg-secondary-container" : "bg-error"} animate-pulse`} />
            <span className="font-label-md text-label-md text-on-surface">
              <strong className="font-semibold">Step 8 of 9: Design Import &amp; Slot Binding</strong>
              {d ? ` • ${placedCount}/${total} visuals bound • ${complete ? "mapping complete" : dirty ? "unsaved changes" : "mapping incomplete"}` : " • Importing…"}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 justify-end">
            <Link
              href={`/project/design-method?project=${projectId}`}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md flex items-center gap-1.5"
            >
              <Icon name="arrow_back" className="text-[16px]" /> Back: Design Method
            </Link>
            <button
              type="button"
              disabled={!dirty || busy !== null}
              onClick={() => run("save", () => saveDesignMapping(projectId, mapping))}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md flex items-center gap-1.5 disabled:opacity-50"
            >
              <Icon name="save" className="text-[16px]" /> Save Draft
            </button>
            <button
              type="button"
              disabled={!data}
              onClick={exportMapping}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md flex items-center gap-1.5 disabled:opacity-50"
            >
              <Icon name="data_object" className="text-[16px]" /> Export Mapping (.json)
            </button>
            {complete ? (
              <PillButton href={`/project/build?project=${projectId}`} arrow>
                Next: Build PBIP
              </PillButton>
            ) : (
              <PillButton arrow disabled title={dirty ? "Save the mapping first" : "Every visual needs exactly one box, inside the canvas, with no overlaps"}>
                Next: Build PBIP
              </PillButton>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
