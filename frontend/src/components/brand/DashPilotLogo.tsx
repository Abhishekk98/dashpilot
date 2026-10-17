/**
 * Recreation of the "DashPilot AI" logo pill from the designs.
 * The Stitch export hot-links the logo from googleusercontent.com, so it is
 * rebuilt here in markup; swap for an exported asset once one is available.
 */
export function DashPilotLogo() {
  return (
    <span className="inline-flex h-7 items-center gap-1.5 rounded-full border border-on-surface/80 bg-surface-container-lowest pl-1 pr-1.5">
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-charcoal">
        <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden="true">
          <path d="M6 1.5 10.5 10H8.2L6 5.6 3.8 10H1.5z" fill="#F8CF4B" />
        </svg>
      </span>
      <span className="font-body-md text-[10px] font-semibold leading-none text-on-surface">DashPilot</span>
      <span className="rounded-full bg-secondary-fixed/60 px-1.5 py-0.5 text-[7px] font-semibold leading-none text-on-surface">
        AI
      </span>
    </span>
  );
}
