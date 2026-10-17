import type { ReactNode } from "react";

interface StatNumberProps {
  label: string;
  value: ReactNode;
  /** Small unit after the value, e.g. "live", "gen", "hrs". */
  unit?: string;
  /** Icon or badge rendered before the label. */
  icon?: ReactNode;
  size?: "huge" | "xl";
  className?: string;
}

/** Large light-weight Outfit metric with an uppercase label (Home telemetry metrics). */
export function StatNumber({ label, value, unit, icon, size = "huge", className = "" }: StatNumberProps) {
  const valueClass =
    size === "huge"
      ? "font-metric-huge text-metric-huge-mobile md:text-metric-huge"
      : "font-headline-xl text-headline-xl";
  return (
    <div className={`flex flex-col ${className}`}>
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className={`${valueClass} text-primary font-light`}>{value}</span>
        {unit && <span className="text-on-surface-variant font-label-md text-label-md">{unit}</span>}
      </div>
    </div>
  );
}
