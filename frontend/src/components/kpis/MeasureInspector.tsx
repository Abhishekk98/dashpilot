"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { Measure, MeasureFormat, MeasureInput } from "@/lib/api";
import { FOLDERS, FORMAT_LABELS, SOURCE_LABELS, highlightDax } from "@/lib/dax";

interface MeasureInspectorProps {
  measure: Measure | null;
  /** Inspector opens in edit mode for a brand-new measure. */
  creating: boolean;
  generated: boolean;
  busy: boolean;
  aiAvailable: boolean;
  onSave: (data: MeasureInput, originalName?: string) => Promise<boolean>;
  onCancelNew: () => void;
  onRegenerate: () => void;
  onDelete: () => void;
  onPolish: () => void;
}

const EMPTY: MeasureInput = { name: "", expression: "", format: "decimal", folder: "05 Custom", description: "" };

const chip = "px-2.5 py-1 rounded-full bg-inverse-surface font-code-sm text-code-sm text-inverse-on-surface";
const darkButton = "px-4 py-2 rounded-full bg-inverse-surface hover:bg-outline text-inverse-on-surface font-label-md text-label-md transition-colors disabled:opacity-50";
const field = "w-full px-3 py-2 rounded-xl bg-inverse-surface text-inverse-on-surface font-code-md text-code-md outline-none focus:ring-2 focus:ring-secondary-container";

/** Dark "Measure Inspector": formatted DAX, explanation, calculated value, and edit/regenerate/polish. */
export function MeasureInspector({
  measure,
  creating,
  generated,
  busy,
  aiAvailable,
  onSave,
  onCancelNew,
  onRegenerate,
  onDelete,
  onPolish,
}: MeasureInspectorProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<MeasureInput>(EMPTY);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (creating) {
      setDraft(EMPTY);
      setEditing(true);
    } else {
      setEditing(false);
    }
  }, [creating, measure?.name]);

  const startEdit = () => {
    if (!measure) return;
    setDraft({ name: measure.name, expression: measure.expression, format: measure.format, folder: measure.folder, description: measure.description });
    setEditing(true);
  };

  const save = async () => {
    const ok = await onSave(draft, creating ? undefined : measure?.name);
    if (ok && !creating) setEditing(false);
  };

  const copy = async () => {
    if (!measure) return;
    try {
      await navigator.clipboard.writeText(`${measure.name} =\n${measure.expression}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  if (!measure && !creating) {
    return (
      <div className="p-7 rounded-card bg-primary-container text-on-primary shadow-dark font-body-md text-body-md text-on-primary-container">
        Select a measure to inspect its DAX.
      </div>
    );
  }

  return (
    <div className="p-7 rounded-card bg-primary-container text-on-primary shadow-[0_20px_48px_-12px_rgba(0,0,0,0.25)] flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3 pb-1">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="px-3 py-1 rounded-full bg-secondary-container text-on-secondary-fixed font-label-sm text-label-sm font-semibold tracking-wide shrink-0">
            {creating ? "NEW MEASURE" : "MEASURE INSPECTOR"}
          </span>
          {measure && !creating && <span className="font-label-md text-label-md text-on-primary-container truncate">Folder: {measure.folder}</span>}
        </div>
        {measure && !creating && (
          <button type="button" onClick={copy} title="Copy DAX to clipboard" className="w-9 h-9 rounded-full bg-inverse-surface hover:bg-outline text-inverse-on-surface flex items-center justify-center transition-colors shrink-0">
            <Icon name={copied ? "check" : "content_copy"} className="text-[18px]" />
          </button>
        )}
      </div>

      {editing ? (
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="font-label-sm text-label-sm text-on-primary-container">Name</span>
            <input
              value={draft.name}
              disabled={generated && !creating}
              maxLength={100}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="e.g. Repeat Customer Rate"
              className={`${field} disabled:opacity-60`}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-label-sm text-label-sm text-on-primary-container">DAX formula</span>
            <textarea
              value={draft.expression}
              rows={9}
              spellCheck={false}
              onChange={(e) => setDraft({ ...draft, expression: e.target.value })}
              placeholder={"DIVIDE(\n    [Total Revenue],\n    [Total Orders]\n)"}
              className={`${field} resize-y leading-relaxed`}
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="font-label-sm text-label-sm text-on-primary-container">Format</span>
              <select value={draft.format} onChange={(e) => setDraft({ ...draft, format: e.target.value as MeasureFormat })} className={field}>
                {(Object.keys(FORMAT_LABELS) as MeasureFormat[]).map((f) => (
                  <option key={f} value={f}>
                    {FORMAT_LABELS[f]}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-label-sm text-label-sm text-on-primary-container">Display folder</span>
              <select value={draft.folder} onChange={(e) => setDraft({ ...draft, folder: e.target.value })} className={field}>
                {FOLDERS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className="font-label-sm text-label-sm text-on-primary-container">Business meaning</span>
            <textarea
              value={draft.description}
              rows={2}
              maxLength={600}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              className={`${field} font-body-md text-body-md resize-y`}
            />
          </label>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              disabled={busy || !draft.name.trim() || !draft.expression.trim()}
              onClick={save}
              className="px-4 py-2 rounded-full bg-secondary-container text-on-secondary-fixed font-label-md text-label-md font-semibold flex items-center gap-1.5 disabled:opacity-50"
            >
              <Icon name={busy ? "sync" : "rule"} className={`text-[16px] ${busy ? "animate-spin" : ""}`} />
              Save &amp; Validate
            </button>
            <button type="button" className={darkButton} onClick={() => (creating ? onCancelNew() : setEditing(false))}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        measure && (
          <>
            <div className="flex flex-col gap-2">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-secondary-container font-headline-md text-headline-md font-mono">[</span>
                <span className="font-headline-md text-headline-md text-on-primary font-semibold tracking-tight break-words">{measure.name}</span>
                <span className="text-secondary-container font-headline-md text-headline-md font-mono">]</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={chip}>
                  Format: {FORMAT_LABELS[measure.format]} ({measure.format_string})
                </span>
                <span className={chip}>Deps: {measure.deps.length}</span>
                {measure.time_intelligence && <span className={chip}>Time-Series Safe</span>}
                <span className={chip}>
                  {SOURCE_LABELS[measure.source]}
                  {measure.industry ? ` • ${measure.industry}` : ""}
                  {measure.edited ? " • Edited" : ""}
                </span>
              </div>
            </div>

            <div className="p-5 rounded-[20px] bg-inverse-surface font-code-md text-code-md text-inverse-on-surface leading-relaxed overflow-x-auto shadow-inner">
              <div className="text-on-primary-container select-none mb-1">
                {measure.status === "error" ? "// Rejected by the DAX validator" : measure.status === "edge" ? "// Valid DAX • check edge cases" : "// Validated • calculated on your cleaned data"}
              </div>
              <pre className="whitespace-pre-wrap">
                <code>
                  <span className="text-secondary-container font-semibold">{measure.name}</span> ={"\n"}
                  {highlightDax(measure.expression)}
                </code>
              </pre>
            </div>

            {measure.issues.length > 0 && (
              <ul className={`p-4 rounded-[20px] flex flex-col gap-1.5 font-body-md text-xs ${measure.status === "error" ? "bg-error-container text-on-error-container" : "bg-secondary-container/15 text-secondary-container"}`}>
                {measure.issues.map((i) => (
                  <li key={i} className="flex items-start gap-2">
                    <Icon name={measure.status === "error" ? "error" : "info"} className="text-[14px] mt-0.5 shrink-0" />
                    <span>{i}</span>
                  </li>
                ))}
              </ul>
            )}

            <div className="p-5 rounded-[20px] bg-inverse-surface/60 flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Icon name="psychology" className="text-secondary-container text-[20px]" />
                <span className="font-title-lg text-title-lg text-on-primary font-medium">Business Logic Translation</span>
              </div>
              <p className="font-body-md text-body-md text-on-primary-container leading-relaxed">{measure.description || "No description yet. Use Polish with AI to generate one."}</p>
            </div>

            <div className="px-5 py-4 rounded-[20px] bg-inverse-surface/60 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${measure.status === "passed" ? "bg-secondary-container" : measure.status === "edge" ? "bg-outline" : "bg-coral"}`} />
                <div className="flex flex-col min-w-0">
                  <span className="font-code-sm text-code-sm text-on-primary-container truncate">Test Context: {measure.test_context ?? "not evaluated"}</span>
                  <span className="font-title-lg text-title-lg text-on-primary font-medium truncate">
                    Calculated Value: {measure.status === "error" ? "—" : (measure.value_text ?? "—")}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button type="button" className={darkButton} disabled={busy} onClick={startEdit}>
                Edit Formula
              </button>
              {generated && measure.edited && (
                <button type="button" className={darkButton} disabled={busy} onClick={onRegenerate}>
                  Regenerate
                </button>
              )}
              <button type="button" className={darkButton} disabled={busy} onClick={onDelete} title="Remove this measure">
                <Icon name="delete" className="text-[16px]" />
              </button>
              {aiAvailable && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={onPolish}
                  className="ml-auto px-5 py-2 rounded-full bg-secondary-container text-on-secondary-fixed font-label-md text-label-md font-semibold flex items-center gap-1.5 shadow-sm hover:scale-[1.02] transition-transform disabled:opacity-50"
                >
                  <Icon name={busy ? "sync" : "auto_fix_high"} className={`text-[16px] ${busy ? "animate-spin" : ""}`} />
                  Polish with AI
                </button>
              )}
            </div>
          </>
        )
      )}
    </div>
  );
}
