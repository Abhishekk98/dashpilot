"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PillTag } from "@/components/ui/PillTag";
import {
  type DesignState,
  type DesignVariant,
  generateReferenceDesigns,
  getReference,
  type ReferenceResponse,
  type ReferenceState,
  referenceImageUrl,
  saveStyleProfile,
  type StyleProfile,
  uploadReference,
} from "@/lib/api";

import { DesignFrame, ScaledCanvas } from "./ScaledCanvas";

const field = "w-full px-3 py-1.5 rounded-xl bg-surface-container-low text-on-surface font-body-md text-xs outline-none focus:ring-2 focus:ring-secondary-container";
const ACCEPT = "image/png,image/jpeg,image/webp";

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-surface-container-low">
      <input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} className="w-7 h-7 rounded-lg border-0 bg-transparent cursor-pointer" aria-label={label} />
      <span className="flex flex-col leading-tight">
        <span className="font-label-sm text-[11px] text-on-surface-variant">{label}</span>
        <span className="font-code-sm text-code-sm text-on-surface">{value}</span>
      </span>
    </label>
  );
}

interface Props {
  projectId: string;
  design: DesignState | null;
  blocked: string | null; // why designs cannot be generated right now (unsaved / invalid plan)
  selecting: boolean;
  onSelect: (variantId: string) => void;
  onPreview: (v: DesignVariant) => void;
}

/** Design method C: reference image → editable style profile → two designs in that style. */
export function OptionCPanel({ projectId, design, blocked, selecting, onSelect, onPreview }: Props) {
  const [state, setState] = useState<ReferenceState | null>(null);
  const [draft, setDraft] = useState<StyleProfile | null>(null);
  const [busy, setBusy] = useState<null | "upload" | "save" | "generate">(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = (res: ReferenceResponse) => {
    setState(res.state);
    setDraft(res.state.profile);
    setNotes(res.notes);
  };

  useEffect(() => {
    let alive = true;
    getReference(projectId)
      .then((res) => alive && load(res))
      .catch((e) => alive && setError((e as Error).message));
    return () => {
      alive = false;
    };
  }, [projectId]);

  const dirty = useMemo(() => !!draft && !!state?.profile && JSON.stringify(draft) !== JSON.stringify(state.profile), [draft, state]);

  const run = async (kind: NonNullable<typeof busy>, action: () => Promise<ReferenceResponse>) => {
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

  const upload = (file: File | undefined) => {
    if (!file) return;
    if (!ACCEPT.split(",").includes(file.type)) {
      setError("Upload a PNG, JPG or WebP screenshot of a dashboard you like.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("Reference images must be 10 MB or smaller.");
      return;
    }
    void run("upload", () => uploadReference(projectId, file));
  };

  const set = (patch: Partial<StyleProfile>) => draft && setDraft({ ...draft, ...patch });
  const p = draft;
  const variants = state?.variants ?? [];

  return (
    <div className="flex flex-col gap-5">
      {error && (
        <div role="alert" className="p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}
      {notes.length > 0 && (
        <div role="status" className="p-3 rounded-inner bg-surface-container-lowest/80 shadow-card flex flex-col gap-1">
          {notes.map((n) => (
            <p key={n} className="flex items-start gap-2 font-body-md text-xs text-on-surface">
              <Icon name="info" className="text-[16px] text-secondary shrink-0" /> <span>{n}</span>
            </p>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        {/* reference image */}
        <div className="xl:col-span-5 flex flex-col gap-3">
          <input ref={fileRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files?.[0]); }}
            className={`relative w-full aspect-video rounded-card overflow-hidden border-2 border-dashed flex items-center justify-center transition-colors ${drag ? "border-secondary bg-secondary-container/20" : "border-outline-variant bg-surface-container-lowest/80 hover:bg-surface-container-low"}`}
          >
            {state?.image ? (
              // eslint-disable-next-line @next/next/no-img-element -- user-uploaded reference, served by the API
              <img src={referenceImageUrl(projectId, state.image.sha)} alt="Reference dashboard" className="absolute inset-0 w-full h-full object-contain bg-surface-container-low" />
            ) : (
              <span className="flex flex-col items-center gap-2 px-6 text-center">
                <Icon name={busy === "upload" ? "sync" : "add_photo_alternate"} className={`text-[36px] text-on-surface-variant ${busy === "upload" ? "animate-spin" : ""}`} />
                <span className="font-title-lg text-title-lg text-on-surface font-semibold">Upload a reference dashboard</span>
                <span className="font-body-md text-xs text-on-surface-variant">PNG, JPG or WebP up to 10 MB. Only its style is used, never its layout, text or logos.</span>
              </span>
            )}
            {busy === "upload" && state?.image && <span className="absolute inset-0 bg-surface-container-lowest/70 flex items-center justify-center font-label-md text-label-md">Reading the style…</span>}
          </button>
          {state?.image && (
            <div className="flex items-center justify-between gap-2 px-1">
              <span className="font-code-sm text-code-sm text-on-surface-variant truncate">
                {state.image.filename} • {state.image.width}×{state.image.height}
              </span>
              <button type="button" disabled={busy !== null} onClick={() => fileRef.current?.click()} className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface flex items-center gap-1 shrink-0">
                <Icon name="sync" className="text-[15px]" /> Replace image
              </button>
            </div>
          )}
        </div>

        {/* style profile */}
        <div className="xl:col-span-7 p-5 rounded-card bg-surface-container-lowest/90 shadow-card flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-title-lg text-title-lg text-on-surface font-semibold flex items-center gap-2">
              <Icon name="style" className="text-[20px]" /> Style profile
            </h3>
            {p && (
              <PillTag tone={p.source === "ai" ? "accent" : "neutral"} size="md">
                {p.source === "ai" ? "Colors + AI vision" : "Colors from image"}{state?.edited ? " · edited" : ""}
              </PillTag>
            )}
          </div>
          {!p ? (
            <p className="font-body-md text-body-md text-on-surface-variant">Upload a reference image to read its colors, card style, corners, shadows, fonts and spacing. You can edit everything before generating.</p>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                <ColorField label="Background" value={p.background.colors[0]} onChange={(v) => set({ background: { ...p.background, colors: [v, ...p.background.colors.slice(1)] } })} />
                {p.background.type === "gradient" && (
                  <ColorField label="Background 2" value={p.background.colors[1] ?? p.background.colors[0]} onChange={(v) => set({ background: { ...p.background, colors: [p.background.colors[0], v] } })} />
                )}
                <ColorField label="Cards" value={p.card_color} onChange={(v) => set({ card_color: v })} />
                <ColorField label="Accent" value={p.palette.primary} onChange={(v) => set({ palette: { ...p.palette, primary: v } })} />
                <ColorField label="Text" value={p.palette.text} onChange={(v) => set({ palette: { ...p.palette, text: v } })} />
                <ColorField label="Muted" value={p.palette.muted} onChange={(v) => set({ palette: { ...p.palette, muted: v } })} />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <label className="flex flex-col gap-1">
                  <span className="font-label-sm text-[11px] text-on-surface-variant">Card style</span>
                  <select className={field} value={p.card_style} onChange={(e) => set({ card_style: e.target.value as StyleProfile["card_style"] })}>
                    <option value="elevated">Elevated</option>
                    <option value="solid">Solid</option>
                    <option value="outlined">Outlined</option>
                    <option value="glass">Glass</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="font-label-sm text-[11px] text-on-surface-variant">Corner radius: {p.radius_px}px</span>
                  <input type="range" min={0} max={40} value={p.radius_px} onChange={(e) => set({ radius_px: Number(e.target.value) })} className="accent-secondary mt-1" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="font-label-sm text-[11px] text-on-surface-variant">Shadow</span>
                  <select className={field} value={p.shadow} onChange={(e) => set({ shadow: e.target.value as StyleProfile["shadow"] })}>
                    <option value="none">None</option>
                    <option value="soft">Soft</option>
                    <option value="deep">Deep</option>
                    <option value="glow">Glow</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="font-label-sm text-[11px] text-on-surface-variant">Headings</span>
                  <select className={field} value={p.font_character} onChange={(e) => set({ font_character: e.target.value as StyleProfile["font_character"] })}>
                    <option value="geometric sans">Geometric sans</option>
                    <option value="humanist sans">Humanist sans</option>
                    <option value="serif">Serif</option>
                    <option value="mono">Mono</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="font-label-sm text-[11px] text-on-surface-variant">Spacing</span>
                  <select className={field} value={p.spacing} onChange={(e) => set({ spacing: e.target.value as StyleProfile["spacing"] })}>
                    <option value="compact">Compact</option>
                    <option value="regular">Regular</option>
                    <option value="airy">Airy</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="font-label-sm text-[11px] text-on-surface-variant">Mode</span>
                  <select className={field} value={p.mode} onChange={(e) => set({ mode: e.target.value as StyleProfile["mode"] })}>
                    <option value="light">Light</option>
                    <option value="dark">Dark</option>
                  </select>
                </label>
              </div>
              {p.layout_pattern && (
                <p className="font-body-md text-[11px] text-on-surface-variant flex items-start gap-1.5">
                  <Icon name="info" className="text-[14px] shrink-0" /> Reference layout ({p.layout_pattern}) is not copied; the layout comes from your plan.
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2.5">
                {dirty && (
                  <>
                    <PillButton variant="secondary" icon={busy === "save" ? "sync" : "save"} disabled={busy !== null} onClick={() => draft && run("save", () => saveStyleProfile(projectId, draft))}>
                      Save profile
                    </PillButton>
                    <button type="button" onClick={() => setDraft(state?.profile ?? null)} className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface underline underline-offset-4">
                      Discard
                    </button>
                  </>
                )}
                <PillButton
                  variant="accent"
                  className="ml-auto"
                  icon={busy === "generate" ? "sync" : "auto_awesome"}
                  disabled={busy !== null || dirty || !!blocked}
                  title={dirty ? "Save the profile first" : blocked ?? undefined}
                  onClick={() => run("generate", () => generateReferenceDesigns(projectId))}
                >
                  {busy === "generate" ? "Designing…" : variants.length ? "Regenerate 2 designs" : "Generate 2 designs"}
                </PillButton>
              </div>
            </>
          )}
        </div>
      </div>

      {busy === "generate" && (
        <p className="font-body-md text-xs text-on-surface-variant flex items-center gap-1.5">
          <Icon name="hourglass_top" className="text-[14px]" /> AI designs both variants in the reference style and checks them against the contract; this can take 1–2 minutes.
        </p>
      )}

      {state?.stale && variants.length > 0 && (
        <p className="font-body-md text-body-md text-on-surface-variant">The plan or the style profile changed after these designs were made. Regenerate so they match.</p>
      )}

      {(variants.length > 0 || busy === "generate") && state?.image && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="p-3 rounded-card bg-surface-container-lowest/90 shadow-card flex flex-col gap-3">
            <div className="relative w-full aspect-video rounded-inner overflow-hidden bg-surface-container-low">
              {/* eslint-disable-next-line @next/next/no-img-element -- user-uploaded reference */}
              <img src={referenceImageUrl(projectId, state.image.sha)} alt="Reference" className="w-full h-full object-cover" />
            </div>
            <div className="flex items-center justify-between gap-2 px-1 pb-1">
              <span className="font-title-lg text-[15px] text-on-surface font-semibold">Reference</span>
              <PillTag size="md">Style source</PillTag>
            </div>
          </div>
          {busy === "generate"
            ? [0, 1].map((n) => <div key={n} className="aspect-video rounded-card bg-hatched animate-pulse" />)
            : variants.map((v) => {
                const chosen = design?.selected === v.id;
                return (
                  <div key={v.id} className={`p-3 rounded-card bg-surface-container-lowest/90 shadow-card flex flex-col gap-3 ${chosen ? "ring-2 ring-primary-container" : ""} ${state.stale ? "opacity-60" : ""}`}>
                    <button type="button" onClick={() => onPreview(v)} className="block rounded-inner overflow-hidden" aria-label={`Open ${v.label} full size`}>
                      <ScaledCanvas>
                        <DesignFrame html={v.html} title={v.label} />
                      </ScaledCanvas>
                    </button>
                    <div className="flex items-center justify-between gap-2 px-1">
                      <div className="flex flex-col min-w-0">
                        <span className="font-title-lg text-[15px] text-on-surface font-semibold">{v.label}</span>
                        <span className="font-body-md text-[11px] text-on-surface-variant truncate" title={v.note ?? undefined}>
                          {v.note ?? (v.source === "ai" ? `AI design in the reference style${v.attempts > 1 ? `, passed on try ${v.attempts}` : ""}` : "Profile-themed template")}
                        </span>
                      </div>
                      <PillTag tone={v.source === "ai" ? "accent" : "neutral"} size="md">{v.source === "ai" ? "AI" : "Template"}</PillTag>
                    </div>
                    <div className="flex items-center gap-2 px-1 pb-1">
                      <PillButton variant={chosen ? "primary" : "secondary"} icon={chosen ? "check_circle" : "radio_button_unchecked"} disabled={selecting || busy !== null || state.stale} onClick={() => onSelect(v.id)}>
                        {chosen ? "Selected" : "Use this design"}
                      </PillButton>
                      <button type="button" onClick={() => onPreview(v)} className="ml-auto font-label-sm text-label-sm text-on-surface-variant hover:text-on-surface flex items-center gap-1">
                        <Icon name="open_in_full" className="text-[14px]" /> Full size
                      </button>
                    </div>
                  </div>
                );
              })}
        </div>
      )}
    </div>
  );
}
