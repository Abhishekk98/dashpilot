import Link from "next/link";

import { Icon } from "@/components/ui/Icon";

export type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";

interface ContextActionBarProps {
  state: SaveState;
  /** Duration of the last successful save, shown like the design's "(34ms)". */
  lastSaveMs: number | null;
  everSaved: boolean;
  backHref: string;
  onSave: () => void;
  onNext: () => void;
}

const STATUS: Record<SaveState, { dot: string; text: (ms: number | null, ever: boolean) => string }> = {
  idle: { dot: "bg-pine", text: (_, ever) => (ever ? "State saved to project workspace" : "Not saved yet") },
  dirty: { dot: "bg-secondary-container", text: () => "Unsaved changes, auto-saving…" },
  saving: { dot: "bg-secondary-container animate-pulse", text: () => "Saving to project workspace…" },
  saved: { dot: "bg-pine", text: (ms) => `State auto-saved to workspace cache${ms !== null ? ` (${ms}ms)` : ""}` },
  error: { dot: "bg-coral", text: () => "Save failed. Try Save Draft again." },
};

/** Sticky bottom dock of the Context screen. */
export function ContextActionBar({ state, lastSaveMs, everSaved, backHref, onSave, onNext }: ContextActionBarProps) {
  const status = STATUS[state];
  return (
    <div className="sticky bottom-4 z-40 w-full mt-2">
      <div className="rounded-panel sm:rounded-full bg-surface-container-lowest/90 backdrop-blur-2xl px-6 py-4 shadow-[0_16px_40px_-10px_rgba(35,35,35,0.18)] flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className={`w-2.5 h-2.5 rounded-full ${status.dot}`} />
          <div className="flex flex-col">
            <span className="font-label-md text-label-md font-semibold text-on-surface">Step 3 of 9 • Business Context &amp; Brand Kit</span>
            <span className="font-code-sm text-code-sm text-on-surface-variant">{status.text(lastSaveMs, everSaved)}</span>
          </div>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
          <Link
            href={backHref}
            className="px-5 py-2.5 rounded-full bg-surface-container-low text-on-surface-variant hover:bg-surface-container hover:text-on-surface font-title-lg text-title-lg transition-all"
          >
            ← Back: Clean Data
          </Link>
          <button
            type="button"
            onClick={onSave}
            disabled={state === "saving"}
            className="hidden md:inline-flex px-4 py-2.5 rounded-full text-on-surface-variant hover:text-on-surface font-title-lg text-title-lg transition-colors disabled:opacity-50"
          >
            Save Draft
          </button>
          <button
            type="button"
            onClick={onNext}
            className="px-6 py-2.5 rounded-full bg-primary-container text-on-primary font-title-lg text-title-lg font-medium flex items-center gap-3 shadow-md hover:scale-[1.02] active:scale-[0.98] transition-all group"
          >
            <span>Next: Model Schema &amp; Relationships</span>
            <span className="w-7 h-7 rounded-full bg-secondary-container text-on-secondary-fixed flex items-center justify-center font-bold transition-transform group-hover:translate-x-0.5">
              <Icon name="arrow_forward" className="text-[16px]" />
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
