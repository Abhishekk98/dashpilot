"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PillTag } from "@/components/ui/PillTag";
import {
  type DesignState,
  designBackgroundUrl,
  designOriginalUrl,
  getStitchPrompt,
  getStitchState,
  type PlanVisual,
  type StitchPrompt,
  type StitchState,
  type StitchStyle,
  uploadStitch,
} from "@/lib/api";

import { FidelityReport } from "./FidelityReport";

interface Props {
  projectId: string;
  visuals: PlanVisual[];
  design: DesignState | null;
  blocked: string | null;
  selecting: boolean;
  onSelect: () => void;
}

/** Design method A: Stitch prompt → copy → design in Stitch → upload export → fidelity report → select. */
export function OptionAPanel({ projectId, visuals, design, blocked, selecting, onSelect }: Props) {
  const [style, setStyle] = useState<StitchStyle>("light_elegant");
  const [prompt, setPrompt] = useState<StitchPrompt | null>(null);
  const [state, setState] = useState<StitchState | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState<null | "prompt" | "upload">("prompt");
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    getStitchState(projectId).then((s) => alive && setState(s)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [projectId]);

  useEffect(() => {
    if (blocked) return;
    let alive = true;
    setBusy("prompt");
    getStitchPrompt(projectId, style)
      .then((p) => alive && setPrompt(p))
      .catch((e) => alive && setError((e as Error).message))
      .finally(() => alive && setBusy(null));
    return () => {
      alive = false;
    };
  }, [projectId, style, blocked]);

  const copy = async () => {
    if (!prompt) return;
    try {
      await navigator.clipboard.writeText(prompt.prompt);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = prompt.prompt;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy("upload");
    setError(null);
    try {
      setState(await uploadStitch(projectId, file));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const d = state?.design ?? null;
  const titles = new Map(visuals.map((v) => [v.id, v.title]));
  const unmatched = d ? d.mapping.filter((m) => m.method === "none").map((m) => titles.get(m.visual_id) ?? m.visual_id) : [];
  const viaAi = d ? d.mapping.filter((m) => m.method === "ai").length : 0;
  const chosen = design?.selected === "stitch";

  return (
    <div className="flex flex-col gap-5">
      {error && (
        <div role="alert" className="p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        {/* 1. prompt */}
        <div className="xl:col-span-7 p-5 rounded-card bg-surface-container-lowest/90 shadow-card flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-title-lg text-title-lg text-on-surface font-semibold flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-primary-container text-secondary-container font-code-sm text-code-sm flex items-center justify-center">1</span>
              Google Stitch prompt
            </h3>
            <div className="flex items-center gap-2">
              <select
                aria-label="Style"
                value={style}
                onChange={(e) => setStyle(e.target.value as StitchStyle)}
                className="px-3 py-1.5 rounded-full bg-surface-container-low text-on-surface font-label-md text-label-md outline-none focus:ring-2 focus:ring-secondary-container"
              >
                {(prompt?.styles ?? [{ id: "light_elegant", label: "Light Elegant" }]).map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
              <PillButton variant="accent" icon={copied ? "check" : "content_copy"} disabled={!prompt || !!blocked} onClick={copy}>
                {copied ? "Copied" : "Copy prompt"}
              </PillButton>
            </div>
          </div>
          {blocked ? (
            <p className="font-body-md text-body-md text-on-surface-variant">{blocked}.</p>
          ) : (
            <textarea
              readOnly
              aria-label="Stitch prompt"
              value={busy === "prompt" && !prompt ? "Writing the prompt…" : (prompt?.prompt ?? "")}
              className="w-full h-72 px-4 py-3 rounded-2xl bg-surface-container-low text-on-surface font-code-sm text-code-sm leading-relaxed outline-none resize-y"
            />
          )}
          <p className="font-body-md text-xs text-on-surface-variant">
            Paste it into <a href="https://stitch.withgoogle.com" target="_blank" rel="noreferrer" className="underline underline-offset-2">Google Stitch</a>, keep the 1280×720 layout and titles as written, then export the design as code (zip or code.html).
          </p>
        </div>

        {/* 2. upload */}
        <div className="xl:col-span-5 flex flex-col gap-3">
          <input ref={fileRef} type="file" accept=".zip,.html,.htm,application/zip,text/html" className="hidden" onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ""; }} />
          <button
            type="button"
            disabled={busy !== null || !!blocked}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); void upload(e.dataTransfer.files?.[0]); }}
            className="w-full min-h-[180px] rounded-card border-2 border-dashed border-outline-variant bg-surface-container-lowest/80 hover:bg-surface-container-low flex flex-col items-center justify-center gap-2 px-6 text-center disabled:opacity-60"
          >
            <span className="w-6 h-6 rounded-full bg-primary-container text-secondary-container font-code-sm text-code-sm flex items-center justify-center">2</span>
            <Icon name={busy === "upload" ? "sync" : "upload_file"} className={`text-[32px] text-on-surface-variant ${busy === "upload" ? "animate-spin" : ""}`} />
            <span className="font-title-lg text-title-lg text-on-surface font-semibold">{busy === "upload" ? "Rendering the Stitch design…" : "Upload the Stitch export"}</span>
            <span className="font-body-md text-xs text-on-surface-variant">The export .zip (code.html + screen.png) or just code.html. Each card is matched to your visuals by its title.</span>
          </button>
          {state?.upload && (
            <div className="px-1 flex items-center justify-between gap-2 font-code-sm text-code-sm text-on-surface-variant">
              <span className="truncate">{state.upload.filename}{state.upload.has_screen ? " • with screen.png" : " • no screenshot"}</span>
              <span>{new Date(state.upload.uploaded_at).toLocaleString()}</span>
            </div>
          )}
          {state?.notes.map((n) => (
            <p key={n} className="flex items-start gap-1.5 font-body-md text-xs text-on-surface"><Icon name="info" className="text-[14px] shrink-0 mt-0.5" /> {n}</p>
          ))}
        </div>
      </div>

      {/* 3. result */}
      {d && (
        <div className="p-5 rounded-card bg-surface-container-lowest/90 shadow-card flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-title-lg text-title-lg text-on-surface font-semibold flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-primary-container text-secondary-container font-code-sm text-code-sm flex items-center justify-center">3</span>
              Stitch design → Power BI page
            </h3>
            <div className="flex flex-wrap items-center gap-2">
              <PillTag tone={unmatched.length ? "warning" : "success"} size="md">
                {d.mapping.length - unmatched.length}/{d.mapping.length} visuals matched{viaAi ? ` (${viaAi} by AI)` : ""}
              </PillTag>
              {d.scale < 0.999 && <PillTag tone="warning" size="md">Scaled to {Math.round(d.scale * 100)}%</PillTag>}
            </div>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {[
              { label: "Stitch design (as rendered)", url: designOriginalUrl(projectId, d.background_version) },
              { label: "Power BI background (dummy charts removed)", url: designBackgroundUrl(projectId, d.background_version) },
            ].map((x) => (
              <figure key={x.label} className="flex flex-col gap-1.5">
                {/* eslint-disable-next-line @next/next/no-img-element -- generated per project */}
                <img src={x.url} alt={x.label} className="w-full aspect-video rounded-inner bg-surface-container-low object-contain shadow-inner" />
                <figcaption className="font-label-sm text-label-sm text-on-surface-variant px-1">{x.label}</figcaption>
              </figure>
            ))}
          </div>
          {d.fidelity && <FidelityReport report={d.fidelity} override={d.fidelity_override} />}
          {unmatched.length > 0 && (
            <p className="flex items-start gap-1.5 font-body-md text-xs text-on-surface">
              <Icon name="warning" className="text-[14px] shrink-0 mt-0.5" /> No card found for: {unmatched.join(", ")}. Place them by hand in Step 8, or regenerate in Stitch with the exact titles.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <PillButton variant={chosen ? "primary" : "secondary"} icon={chosen ? "check_circle" : "radio_button_unchecked"} disabled={selecting || busy !== null} onClick={onSelect}>
              {chosen ? "Selected" : "Use this Stitch design"}
            </PillButton>
            {d.fidelity && !d.fidelity.passed && (
              <span className="font-body-md text-xs text-error">Below the fidelity threshold: the build will need your OK in Step 8.</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
