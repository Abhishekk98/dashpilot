"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import {
  ApiError,
  type BuildCheck,
  buildDownloadUrl,
  buildProject,
  type BuildStatus,
  designBackgroundUrl,
  getBuildStatus,
  getProject,
  type OpenResult,
  type Project,
  saveAndOpen,
} from "@/lib/api";
import { formatNumber } from "@/lib/format";

/** Shown while the build request runs (the server does them in this order). */
const STAGES = [
  "Writing semantic model (TMDL) and Power Query",
  "Adding DAX measures to _Measures",
  "Placing visuals from the slot mapping",
  "Registering background image and theme",
  "Validating against Microsoft's PBIR schemas",
  "Packaging the .pbip project",
];

const STATUS_ICON: Record<BuildCheck["status"], { icon: string; cls: string }> = {
  pass: { icon: "check", cls: "bg-secondary-container text-on-secondary-fixed" },
  warn: { icon: "priority_high", cls: "bg-secondary-container/50 text-on-secondary-container" },
  fail: { icon: "close", cls: "bg-error text-on-error" },
};

function size(bytes: number) {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function Ring({ value, label }: { value: number; label: string }) {
  const r = 70;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative w-[180px] h-[180px]">
      <svg viewBox="0 0 180 180" className="w-full h-full -rotate-90">
        <circle cx="90" cy="90" r={r} fill="none" strokeWidth="14" className="stroke-surface-container-high" />
        <circle cx="90" cy="90" r={r} fill="none" strokeWidth="14" strokeLinecap="round" className="stroke-secondary-container transition-[stroke-dashoffset] duration-700" strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-metric-huge text-[44px] leading-none text-on-surface font-light tracking-tight">{Math.round(value)}%</span>
        <span className="mt-1 font-code-sm text-code-sm text-on-secondary-container uppercase tracking-wider">{label}</span>
      </div>
    </div>
  );
}

/** Step 9 screen: build the PBIP, show the validation checklist and offer the download. */
export function BuildWorkspace() {
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<BuildStatus | null>(null);
  const [dataFolder, setDataFolder] = useState("");
  const [building, setBuilding] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [openFolder, setOpenFolder] = useState("");
  const [opening, setOpening] = useState(false);
  const [opened, setOpened] = useState<OpenResult | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const playbook = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    getProject(projectId).then((p) => alive && setProject(p)).catch(() => undefined);
    getBuildStatus(projectId)
      .then((s) => {
        if (!alive) return;
        setStatus(s);
        setDataFolder(s.build?.data_folder ?? s.default_data_folder);
        setOpenFolder(s.open_folder);
      })
      .catch((e) => alive && setError((e as Error).message || "Could not load the build. Is the backend running?"));
    return () => {
      alive = false;
    };
  }, [projectId]);

  useEffect(() => {
    if (!building) return;
    setStage(0);
    const t = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 900);
    return () => clearInterval(t);
  }, [building]);

  if (!projectId) {
    return (
      <div className="flex flex-col w-full">
        <StepHeader step={9} title="Build & Export" />
        <PlaceholderCard icon="upload_file" title="No project selected" description="Finish the design import in Step 8 first; the build uses its slot mapping." />
        <Link href="/project/upload" className="mt-6 self-center font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
          Go to Step 1: Upload
        </Link>
      </div>
    );
  }

  const run = async () => {
    setBuilding(true);
    setError(null);
    try {
      const s = await buildProject(projectId, dataFolder);
      setStatus(s);
      setDataFolder(s.build?.data_folder ?? dataFolder);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBuilding(false);
    }
  };

  const open = async (overwrite = false) => {
    setOpening(true);
    setOpenError(null);
    setOpened(null);
    try {
      setOpened(await saveAndOpen(projectId, openFolder, overwrite));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && !overwrite && window.confirm(`${e.message}\n\nThe dashboard there will be replaced by this build.`)) {
        setOpening(false);
        return open(true);
      }
      setOpenError((e as Error).message);
    } finally {
      setOpening(false);
    }
  };

  const b = status?.build ?? null;
  const fails = b ? b.checks.filter((c) => c.status === "fail").length : 0;
  const warns = b ? b.checks.filter((c) => c.status === "warn").length : 0;
  const passed = b ? b.checks.filter((c) => c.status !== "fail").length : 0;
  const progress = building ? ((stage + 1) / (STAGES.length + 1)) * 100 : b ? (passed / b.checks.length) * 100 : 0;
  const ok = !!b && b.valid && !status?.stale;
  const time = (offset: number) => {
    if (!b) return "";
    const d = new Date(new Date(b.built_at).getTime() + offset * 1000);
    return d.toLocaleTimeString([], { hour12: false });
  };

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={9} title={project?.name ?? "Build & Export"} projectId={projectId} badge={project ? (ok ? "Ready" : "Draft") : undefined} />

      <header className="w-full mb-7 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
        <div className="flex flex-col gap-2 max-w-3xl">
          <span className="inline-flex items-center gap-2 self-start px-3 py-1 rounded-full bg-surface-container text-on-surface-variant font-code-sm text-code-sm tracking-wider uppercase">
            PBIP Compiler Engine • Power BI Desktop (PBIR) compliant <span className="w-1.5 h-1.5 rounded-full bg-secondary-container" />
          </span>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-light">Build, Validate &amp; Release PBIP Project</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            {b
              ? `DashPilot compiled your model (${b.tables} tables, ${b.measures} DAX measures), bound ${b.visuals} visuals to their slots and packaged a ready-to-open Power BI Project (.pbip).`
              : "DashPilot writes your star schema, DAX measures and designed report page into a Power BI Project (.pbip) and validates every file before you download it."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5 shrink-0">
          <span className="px-3.5 py-1.5 rounded-full bg-surface-container-lowest shadow-sm flex items-center gap-2 text-on-surface-variant font-label-md text-label-md">
            <Icon name="settings_suggest" className="text-[16px]" /> Engine: Microsoft PBIR + TMDL
          </span>
          {b && (
            <span className="px-3.5 py-1.5 rounded-full bg-surface-container-lowest shadow-sm flex items-center gap-2 text-on-surface-variant font-label-md text-label-md">
              <span className="w-2 h-2 rounded-full bg-secondary-container" /> SHA-256 Verified
            </span>
          )}
        </div>
      </header>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}
      {status && !status.ready && (
        <div role="status" className="mb-6 p-4 rounded-inner bg-surface-container-lowest/80 shadow-card flex flex-col gap-2">
          {status.blockers.map((m) => (
            <p key={m} className="flex items-start gap-2 font-body-md text-body-md text-on-surface">
              <Icon name="info" className="text-[18px] text-secondary shrink-0" /> {m}
            </p>
          ))}
          <Link href={`/project/design-import?project=${projectId}`} className="self-start font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
            Go to Step 8: Design Import
          </Link>
        </div>
      )}
      {status?.stale && b && (
        <div role="status" className="mb-6 p-4 rounded-inner bg-secondary-container/30 text-on-surface flex items-center gap-3">
          <Icon name="update" className="text-[20px]" />
          <span className="font-body-md text-body-md">The plan, mapping or design changed after this build. Build again to include the changes.</span>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 w-full mb-8">
        {/* Compiler pipeline */}
        <section className="xl:col-span-5 rounded-[28px] bg-surface-container-lowest p-6 shadow-[0_12px_36px_-8px_rgba(35,35,35,0.06)] flex flex-col gap-5">
          <div className="flex items-center justify-between">
            <h2 className="font-title-lg text-title-lg text-on-surface font-semibold flex items-center gap-2">
              <Icon name="construction" className="text-[20px]" /> Compiler Pipeline
            </h2>
            <span className="px-2.5 py-0.5 rounded-full bg-secondary-fixed/50 text-on-secondary-fixed font-code-sm text-code-sm font-semibold uppercase">
              Phase: {building ? "Compiling" : ok ? "Finalized" : b ? (fails ? "Needs fixes" : "Outdated") : "Ready"}
            </span>
          </div>

          <div className="rounded-2xl bg-surface-container-low p-6 flex flex-col items-center gap-4">
            <Ring value={progress} label={building ? "Compiling" : ok ? "Ready to deploy" : b ? (fails ? `${fails} failed` : "Rebuild") : "Not built"} />
            <p className="font-body-md text-body-md text-on-surface-variant text-center min-h-[40px]">
              {building ? STAGES[stage] + "…" : b ? `Compiled report definitions & theme (PBIR) into ${b.file_count} files.` : "Choose where the data folder will live, then build."}
            </p>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="font-label-md text-label-md text-on-surface">Data folder on your PC</span>
            <input
              value={dataFolder}
              onChange={(e) => setDataFolder(e.target.value)}
              spellCheck={false}
              className="w-full px-4 py-2.5 rounded-2xl bg-surface-container-low text-on-surface font-code-sm text-code-sm outline-none focus:ring-2 focus:ring-secondary-container"
            />
            <span className="font-body-md text-[11px] text-on-surface-variant">
              The <code>DataFolder</code> parameter&apos;s starting value. You rarely need to change it: <code>Open Dashboard.cmd</code> in the zip and <em>Save &amp; Open in Power BI</em> both point it at the real <code>Data</code> folder.
            </span>
          </label>
          <PillButton icon={building ? "sync" : "build"} disabled={building || !status?.ready || !dataFolder.trim()} onClick={run} className="self-start">
            {building ? "Building…" : b ? "Build again" : "Build PBIP"}
          </PillButton>

          {b && (
            <ul className="flex flex-col gap-2.5">
              {b.checks.map((c) => (
                <li key={c.id} className={`px-4 py-3 rounded-2xl flex flex-col gap-1.5 ${c.status === "fail" ? "bg-error-container/40" : c.status === "warn" ? "bg-secondary-fixed/30" : "bg-surface-container-low"}`}>
                  <div className="flex items-center gap-3">
                    <span className={`w-6 h-6 shrink-0 rounded-full flex items-center justify-center ${STATUS_ICON[c.status].cls}`}>
                      <Icon name={STATUS_ICON[c.status].icon} className="text-[15px]" />
                    </span>
                    <span className="flex-1 font-label-md text-label-md text-on-surface">{c.label}</span>
                    <span className="px-2.5 py-0.5 rounded-full bg-surface-container-lowest font-code-sm text-code-sm text-on-surface-variant whitespace-nowrap">{c.detail}</span>
                  </div>
                  {c.issues.length > 0 && (
                    <ul className="pl-9 flex flex-col gap-0.5">
                      {c.issues.slice(0, 6).map((i) => (
                        <li key={i} className="font-code-sm text-[11px] text-on-surface-variant break-all">{i}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}

          {b && (
            <div className="rounded-2xl bg-primary-container p-4 font-code-sm text-code-sm text-on-primary/90 flex flex-col gap-1 overflow-x-auto">
              <span className="flex items-center justify-between text-on-primary/60 uppercase tracking-wider text-[10px]">
                <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-secondary-container" /> PBIP build log</span>
                <span>dashpilot</span>
              </span>
              <span className="whitespace-nowrap">[{time(0)}] INFO: Wrote {b.tables} TMDL tables, {b.partitions} Power Query partitions</span>
              <span className="whitespace-nowrap">[{time(0)}] SUCCESS: Bound {b.bindings} fields across {b.visuals} visuals</span>
              <span className="whitespace-nowrap">[{time(1)}] {fails ? "ERROR" : "CHECK"}: {passed}/{b.checks.length} validations passed{warns ? `, ${warns} warning${warns > 1 ? "s" : ""}` : ""}</span>
              <span className="whitespace-nowrap">[{time(1)}] {b.valid ? "READY" : "BLOCKED"}: {b.zip_name} ({size(b.size_bytes)})</span>
            </div>
          )}
        </section>

        {/* Result */}
        <section className="xl:col-span-7 rounded-[28px] bg-surface-container-lowest p-6 shadow-[0_12px_36px_-8px_rgba(35,35,35,0.06)] flex flex-col gap-5">
          <div className="rounded-2xl bg-surface-container-low px-5 py-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className={`w-9 h-9 rounded-full flex items-center justify-center ${ok ? "bg-secondary-container text-on-secondary-fixed" : "bg-surface-container-high text-on-surface-variant"}`}>
                <Icon name={ok ? "verified" : b ? "error" : "hourglass_empty"} className="text-[20px]" />
              </span>
              <div className="flex flex-col">
                <span className="font-label-md text-label-md text-on-surface font-semibold uppercase tracking-wide">
                  {ok ? "Build completed & verified" : b ? (fails ? "Build needs fixes" : "Build out of date") : "Not built yet"}
                </span>
                <span className="font-code-sm text-code-sm text-on-surface-variant">Ready for Microsoft Power BI Desktop (PBIP / PBIR)</span>
              </div>
            </div>
            {b && <span className="px-3 py-1 rounded-full bg-surface-container-lowest font-code-sm text-code-sm text-on-surface-variant">Digest: {b.digest.slice(0, 8)}…{b.digest.slice(-3)}</span>}
          </div>

          <div className="rounded-2xl bg-surface-container-low p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="px-3 py-1 rounded-full bg-primary-container text-on-primary font-code-sm text-code-sm flex items-center gap-1.5">
                <Icon name="folder" className="text-[14px] text-secondary-container" /> {status?.project_folder ?? "Project"}.pbip
              </span>
              <span className="font-code-sm text-code-sm text-on-surface-variant">16:9 Native Layout • 1280×720</span>
            </div>
            <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-surface-container shadow-inner">
              {/* eslint-disable-next-line @next/next/no-img-element -- generated per project */}
              <img src={designBackgroundUrl(projectId, b?.built_at ?? "0")} alt="Report page background" className="w-full h-full object-cover" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
              {!b && <div className="absolute inset-0 bg-hatched/40" />}
            </div>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { v: b ? String(fails) : "–", l: fails ? "Errors" : "Errors (all validated)" },
              { v: b ? formatNumber(b.measures) : "–", l: "DAX measures" },
              { v: b ? formatNumber(b.visuals) : "–", l: "Visual containers" },
              { v: b ? formatNumber(b.bindings) : "–", l: "Field bindings" },
            ].map((s) => (
              <div key={s.l} className="rounded-2xl bg-surface-container-low px-4 py-4 flex flex-col items-center text-center gap-0.5">
                <span className="font-headline-md text-headline-md text-on-surface font-semibold">{s.v}</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">{s.l}</span>
              </div>
            ))}
          </div>

          {ok ? (
            <a href={buildDownloadUrl(projectId)} className="rounded-2xl bg-primary-container text-on-primary px-5 py-4 flex items-center justify-between gap-4 hover:opacity-95 transition-opacity">
              <span className="flex items-center gap-4">
                <span className="w-10 h-10 rounded-xl bg-on-primary/10 flex items-center justify-center"><Icon name="folder_zip" className="text-[22px] text-secondary-container" /></span>
                <span className="flex flex-col">
                  <span className="font-title-lg text-title-lg font-semibold">Download Power BI Project (.zip)</span>
                  <span className="font-code-sm text-code-sm text-on-primary/70">{size(b.size_bytes)} • {b.file_count} files • .Report + .SemanticModel + Data</span>
                </span>
              </span>
              <span className="w-10 h-10 rounded-full bg-secondary-container text-on-secondary-fixed flex items-center justify-center"><Icon name="download" className="text-[20px]" /></span>
            </a>
          ) : (
            <div className="rounded-2xl bg-surface-container-high text-on-surface-variant px-5 py-4 flex items-center gap-4">
              <Icon name="folder_zip" className="text-[22px]" />
              <span className="font-title-lg text-title-lg">{b ? (fails ? "Fix the failed checks, then build again" : "Build again to download") : "Build the project to download it"}</span>
            </div>
          )}

          <div className="rounded-2xl bg-surface-container-low p-4 flex flex-col gap-3">
            <div className="flex items-center gap-2 font-label-md text-label-md text-on-surface font-semibold">
              <Icon name="open_in_new" className="text-[18px]" /> Save &amp; Open in Power BI
            </div>
            <div className="flex flex-col sm:flex-row gap-2.5">
              <input
                aria-label="Folder to save the project in"
                value={openFolder}
                onChange={(e) => setOpenFolder(e.target.value)}
                spellCheck={false}
                className="flex-1 min-w-0 px-4 py-2.5 rounded-2xl bg-surface-container-lowest text-on-surface font-code-sm text-code-sm outline-none focus:ring-2 focus:ring-secondary-container"
              />
              <PillButton icon={opening ? "sync" : "rocket_launch"} disabled={!ok || opening || !openFolder.trim()} onClick={() => open()} className="shrink-0">
                {opening ? "Opening…" : "Save & Open"}
              </PillButton>
            </div>
            <span className="font-body-md text-[11px] text-on-surface-variant">
              Saves the project on this PC with its data folder set to <code>{openFolder ? `${openFolder.replace(/[\\/]+$/, "")}\\Data\\` : "…\\Data\\"}</code> and opens it in Power BI Desktop.
            </span>
            {opened && (
              <p role="status" className="flex items-start gap-2 font-body-md text-body-md text-on-surface">
                <Icon name={opened.launched ? "check_circle" : "info"} className="text-[18px] text-secondary shrink-0 mt-0.5" />
                <span>{opened.message} <code className="font-code-sm text-code-sm text-on-surface-variant break-all">{opened.pbip}</code></span>
              </p>
            )}
            {openError && (
              <p role="alert" className="flex items-start gap-2 font-body-md text-body-md text-on-error-container">
                <Icon name="error" className="text-[18px] shrink-0 mt-0.5" /> {openError}
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <span title="Documentation PDF comes in a later version" className="rounded-2xl bg-surface-container-low px-4 py-3 flex items-center justify-center gap-2 font-label-md text-label-md text-on-surface-variant/60 cursor-not-allowed">
              <Icon name="picture_as_pdf" className="text-[16px]" /> Model PDF Guide · soon
            </span>
            <button type="button" onClick={() => playbook.current?.scrollIntoView({ behavior: "smooth" })} className="rounded-2xl bg-surface-container-low hover:bg-surface-container px-4 py-3 flex items-center justify-center gap-2 font-label-md text-label-md text-on-surface">
              <Icon name="help" className="text-[16px]" /> How to Open in PBI Desktop
            </button>
            <span title="Fabric Git sync comes in a later version" className="rounded-2xl bg-surface-container-low px-4 py-3 flex items-center justify-center gap-2 font-label-md text-label-md text-on-surface-variant/60 cursor-not-allowed">
              <Icon name="sync_alt" className="text-[16px]" /> Git Sync to Fabric · soon
            </span>
          </div>
        </section>
      </div>

      <section ref={playbook} className="w-full rounded-[28px] bg-surface-container-lowest p-6 shadow-sm mb-8 flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-code-sm text-code-sm uppercase tracking-wider text-on-surface flex items-center gap-2">
            <Icon name="lightbulb" className="text-[16px]" /> Execution playbook: opening in Power BI Desktop
          </span>
          <span className="font-code-sm text-code-sm text-on-surface-variant">Compatibility: Power BI Desktop 2024+ (PBIR)</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { n: "01", icon: "unarchive", t: "Unzip Anywhere", d: "Extract the zip to any folder (spaces are fine), or skip steps 1–2 with Save & Open in Power BI above." },
            { n: "02", icon: "mouse", t: "Run Open Dashboard.cmd", d: `It points the DataFolder parameter at the Data folder next to it and opens ${status?.project_folder ?? "Project"}.pbip in Power BI Desktop.` },
            { n: "03", icon: "refresh", t: "Refresh, Edit & Publish", d: "Click Refresh to load the data. Visuals, slicers, relationships and DAX measures arrive bound and editable." },
          ].map((s) => (
            <div key={s.n} className="rounded-2xl bg-surface-container-low p-5 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="w-7 h-7 rounded-full bg-primary-container text-secondary-container font-code-sm text-code-sm font-bold flex items-center justify-center">{s.n}</span>
                <Icon name={s.icon} className="text-[18px] text-on-surface-variant" />
              </div>
              <h3 className="font-title-lg text-title-lg text-on-surface font-medium">{s.t}</h3>
              <p className="font-body-md text-body-md text-on-surface-variant">{s.d}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="sticky bottom-4 z-40 w-full">
        <div className="p-4 md:px-7 rounded-panel md:rounded-full bg-surface-container-lowest/90 backdrop-blur-xl shadow-[0_16px_40px_-8px_rgba(35,35,35,0.18)] flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className={`w-2.5 h-2.5 rounded-full ${ok ? "bg-secondary-container" : "bg-outline-variant"}`} />
            <span className="font-label-md text-label-md text-on-surface">
              <strong className="font-semibold">Step 9 of 9 • {ok ? "Power BI Build Complete" : "Build & Export"}</strong>
              {b ? ` • ${passed}/${b.checks.length} pipeline validations passed${ok ? " • Ready for deployment" : ""}` : ""}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 justify-end">
            <Link
              href={`/project/design-import?project=${projectId}`}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md flex items-center gap-1.5"
            >
              <Icon name="arrow_back" className="text-[16px]" /> Back: Visual Mapping
            </Link>
            <PillButton href="/projects" arrow>
              Finished: Go to Projects
            </PillButton>
          </div>
        </div>
      </div>
    </div>
  );
}
