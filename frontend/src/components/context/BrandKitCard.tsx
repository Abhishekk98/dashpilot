"use client";

import { useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { BrandPalette, BusinessContext } from "@/lib/api";
import { FONT_STACKS, SWATCHES } from "@/lib/context";

interface BrandKitCardProps {
  context: BusinessContext;
  logoSrc: string | null;
  onChange: (patch: Partial<BusinessContext>) => void;
  onLogo: (file: File) => void;
  onRemoveLogo: () => void;
  onSuggestPalette: () => void;
  suggesting: boolean;
  /** Rationale or fallback note from the last palette suggestion. */
  paletteNote: string | null;
}

/** Relative luminance check so the swatch tick stays visible on light and dark colours. */
function isLight(hex: string): boolean {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 150;
}

/** Right card: logo, 5 report swatches, AI palette, report mode and font stack. */
export function BrandKitCard({
  context,
  logoSrc,
  onChange,
  onLogo,
  onRemoveLogo,
  onSuggestPalette,
  suggesting,
  paletteNote,
}: BrandKitCardProps) {
  const [selected, setSelected] = useState<keyof BrandPalette>("accent");
  const fileInput = useRef<HTMLInputElement>(null);
  const colorInput = useRef<HTMLInputElement>(null);
  const initial = (context.company_name.trim()[0] ?? "D").toUpperCase();

  const setColor = (hex: string) => onChange({ palette: { ...context.palette, [selected]: hex.toUpperCase() } });

  return (
    <div className="rounded-card bg-surface-container-lowest/75 backdrop-blur-xl p-7 shadow-card flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3 pb-2">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-secondary-container/40 text-on-surface flex items-center justify-center shrink-0">
            <Icon name="palette" className="text-[20px]" />
          </div>
          <div>
            <h2 className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight">Brand Kit &amp; Visual Theming</h2>
            <p className="font-body-md text-body-md text-on-surface-variant">Inject company visuals into Power BI JSON theme files.</p>
          </div>
        </div>
        <span className="px-2.5 py-1 rounded-full bg-secondary-container font-label-sm text-label-sm text-on-secondary-fixed font-semibold shrink-0">
          Active Kit
        </span>
      </div>

      <div className="flex items-center gap-5 p-4 rounded-2xl bg-surface-container-low/60">
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          aria-label="Upload logo"
          className="relative w-20 h-20 rounded-full bg-surface-container-lowest shadow-sm flex flex-col items-center justify-center p-2 text-center shrink-0 hover:bg-secondary-container/20 transition-colors overflow-hidden"
        >
          {logoSrc ? (
            // Uploaded logos are served by the backend; next/image would need a remote-host config.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={logoSrc} alt="Organization logo" className="max-w-full max-h-full object-contain" />
          ) : (
            <>
              <span className="w-10 h-10 rounded-full bg-primary-container text-secondary-container flex items-center justify-center font-headline-md font-semibold text-lg">
                {initial}
              </span>
              <span className="font-code-sm text-[9px] uppercase tracking-tighter text-on-surface-variant mt-0.5">No logo</span>
            </>
          )}
        </button>
        <div className="flex-1 space-y-2 min-w-0">
          <div>
            <div className="font-title-lg text-title-lg text-on-surface font-medium">Organization Mark / Logo</div>
            <p className="font-body-md text-[13px] text-on-surface-variant leading-tight">
              {context.logo ? context.logo.filename : "Drop SVG, transparent PNG or JPG (max 2 MB) for the top navigation banner."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              className="px-4 py-1.5 rounded-full bg-primary-container text-on-primary font-label-md text-label-md hover:opacity-90 transition-opacity"
            >
              {context.logo ? "Replace Brand Mark" : "Upload Brand Mark"}
            </button>
            {context.logo && (
              <button
                type="button"
                title="Remove logo"
                aria-label="Remove logo"
                onClick={onRemoveLogo}
                className="w-8 h-8 rounded-full bg-surface-container-lowest text-on-surface-variant flex items-center justify-center hover:text-error transition-colors"
              >
                <Icon name="delete" className="text-[16px]" />
              </button>
            )}
          </div>
          <input
            ref={fileInput}
            type="file"
            accept=".png,.jpg,.jpeg,.svg,image/png,image/jpeg,image/svg+xml"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onLogo(file);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <span className="font-title-lg text-title-lg text-on-surface">Report Color Swatches</span>
          <span className="font-code-sm text-code-sm text-on-surface-variant">5 Colors • Synced to PBIP</span>
        </div>
        <div className="grid grid-cols-6 gap-2 pt-1">
          {SWATCHES.map(({ key, label }) => {
            const hex = context.palette[key];
            const active = key === selected;
            return (
              <button
                key={key}
                type="button"
                aria-pressed={active}
                onClick={() => setSelected(key)}
                className="flex flex-col items-center gap-1.5 group"
              >
                <span
                  style={{ backgroundColor: hex }}
                  className={`w-11 h-11 rounded-full shadow-sm flex items-center justify-center transition-transform group-hover:scale-105 ${
                    active ? "ring-4 ring-secondary-container/40" : ""
                  }`}
                >
                  {active && <Icon name="check" className={`text-[16px] font-bold ${isLight(hex) ? "text-primary" : "text-on-primary"}`} />}
                </span>
                <span className="font-code-sm text-[11px] text-on-surface font-medium">{hex}</span>
                <span className="font-label-sm text-[10px] text-on-surface-variant uppercase">{label}</span>
              </button>
            );
          })}
          <button type="button" onClick={() => colorInput.current?.click()} className="flex flex-col items-center gap-1.5 group">
            <span className="relative w-11 h-11 rounded-full bg-surface-container-low text-on-surface-variant flex items-center justify-center transition-all group-hover:bg-surface-container group-hover:text-on-surface">
              <Icon name="add" className="text-[20px]" />
              <input
                ref={colorInput}
                type="color"
                aria-label={`Custom ${selected} color`}
                value={context.palette[selected].toLowerCase()}
                onChange={(e) => setColor(e.target.value)}
                className="absolute inset-0 opacity-0 cursor-pointer"
              />
            </span>
            <span className="font-code-sm text-[11px] text-on-surface-variant">Custom</span>
            <span className="font-label-sm text-[10px] text-on-surface-variant uppercase">Hex</span>
          </button>
        </div>
        <button
          type="button"
          disabled={suggesting}
          onClick={onSuggestPalette}
          className="w-full mt-2 py-2.5 px-4 rounded-full bg-secondary-container text-on-secondary-fixed font-title-lg text-title-lg font-medium flex items-center justify-center gap-2 shadow-sm hover:scale-[1.01] active:scale-[0.99] transition-all disabled:opacity-60"
        >
          <Icon name={suggesting ? "sync" : "auto_fix_high"} className={`text-[20px] ${suggesting ? "animate-spin" : ""}`} />
          <span>{suggesting ? "Composing palette…" : "Suggest harmonic palette with AI"}</span>
        </button>
        {paletteNote && <p className="px-1 font-body-md text-xs text-on-surface-variant leading-snug">{paletteNote}</p>}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
        <div className="flex flex-col gap-2 p-3.5 rounded-2xl bg-surface-container-low/60">
          <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">Default Report Mode</span>
          <div className="flex items-center p-1 rounded-full bg-surface-container-lowest shadow-sm">
            {(["light", "dark"] as const).map((mode) => {
              const on = context.mode === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={on}
                  onClick={() => onChange({ mode })}
                  className={`flex-1 py-1.5 px-3 rounded-full font-label-md text-label-md font-medium flex items-center justify-center gap-1.5 transition-colors ${
                    on ? "bg-primary-container text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface"
                  }`}
                >
                  <Icon name={mode === "light" ? "light_mode" : "dark_mode"} className={`text-[16px] ${on ? "text-secondary-container" : ""}`} />
                  <span>{mode === "light" ? "Light" : "Dark"}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex flex-col gap-2 p-3.5 rounded-2xl bg-surface-container-low/60">
          <div className="flex items-center justify-between">
            <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">Font Family Stack</span>
            <span className="font-code-sm text-[10px] text-secondary font-semibold">Native PBIP</span>
          </div>
          <label className="relative p-2 rounded-xl bg-surface-container-lowest flex items-center justify-between cursor-pointer">
            <span className="flex flex-col">
              <span className="font-headline-md text-sm font-semibold text-on-surface">{context.font_stack}</span>
              <span className="font-code-sm text-[10px] text-on-surface-variant">
                {FONT_STACKS.find((f) => f.label === context.font_stack)?.note}
              </span>
            </span>
            <Icon name="tune" className="text-on-surface-variant text-[18px]" />
            <select
              aria-label="Font family stack"
              value={context.font_stack}
              onChange={(e) => onChange({ font_stack: e.target.value })}
              className="absolute inset-0 opacity-0 cursor-pointer"
            >
              {FONT_STACKS.map((f) => (
                <option key={f.label} value={f.label}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </div>
  );
}
