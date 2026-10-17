import type { ReactNode } from "react";

export type PillTagTone = "neutral" | "accent" | "dark" | "success" | "warning" | "error" | "hatched";

const TONES: Record<PillTagTone, string> = {
  neutral: "bg-surface-container text-on-surface-variant",
  accent: "bg-secondary-container text-on-secondary-fixed",
  dark: "bg-primary-container text-on-primary",
  success: "bg-[#E6F4EA] text-[#137333]",
  warning: "bg-secondary-container/30 text-on-secondary-container",
  error: "bg-error-container text-on-error-container",
  hatched: "bg-hatched-neutral text-primary",
};

const DOT_TONES: Record<PillTagTone, string> = {
  neutral: "bg-outline-variant",
  accent: "bg-primary",
  dark: "bg-secondary-container",
  success: "bg-pine",
  warning: "bg-secondary-container",
  error: "bg-coral",
  hatched: "bg-primary",
};

interface PillTagProps {
  tone?: PillTagTone;
  /** Leading status dot. */
  dot?: boolean;
  /** Use JetBrains Mono, as on counters like "3 / 8 Files Ingested". */
  mono?: boolean;
  /** sm: inline status chips; md: header badges and counters. */
  size?: "sm" | "md";
  className?: string;
  children: ReactNode;
}

/** Small rounded-full badge / chip (status, roles, counters). */
export function PillTag({ tone = "neutral", dot = false, mono = false, size = "sm", className = "", children }: PillTagProps) {
  const font = mono ? "font-code-sm text-code-sm" : "font-label-sm text-label-sm";
  const padding = size === "md" ? "px-3 py-1" : "px-2.5 py-0.5";
  return (
    <span className={`inline-flex w-fit items-center gap-1.5 ${padding} rounded-full font-semibold ${font} ${TONES[tone]} ${className}`}>
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${DOT_TONES[tone]}`} />}
      {children}
    </span>
  );
}
