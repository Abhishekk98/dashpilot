/** Thin circular gauge (sunflower fill on a light track) from DESIGN.md "Progress Gauges". */
export function QualityGauge({ value, max = 100, size = 96 }: { value: number; max?: number; size?: number }) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const fraction = Math.min(Math.max(value / max, 0), 1);
  return (
    <div className="relative shrink-0 flex items-center justify-center" style={{ width: size, height: size }}>
      <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="#E3E2E2" strokeWidth="8" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="#F8CF4B"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          className="transition-[stroke-dashoffset] duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-headline-lg text-headline-lg font-light text-on-surface leading-none">{value}</span>
        <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">/ {max}</span>
      </div>
    </div>
  );
}
