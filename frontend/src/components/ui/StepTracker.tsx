import Link from "next/link";

import { Icon } from "./Icon";
import { PIPELINE_STEPS, stepHref } from "@/lib/steps";

/** "Stepper Pipeline Ribbon" from the step designs: the active step is a charcoal pill. */
export function StepTracker({ currentStep, projectId }: { currentStep: number; projectId?: string | null }) {
  // Keep the active project when jumping between steps.
  const href = (step: (typeof PIPELINE_STEPS)[number]) =>
    projectId ? `${stepHref(step)}?project=${projectId}` : stepHref(step);

  return (
    <div className="w-full overflow-x-auto pb-2">
      <div className="flex items-center gap-2 min-w-max p-1.5 rounded-full bg-surface-container-lowest/70 backdrop-blur-xl shadow-ribbon">
        {PIPELINE_STEPS.map((step) =>
          step.number === currentStep ? (
            <Link
              key={step.slug}
              href={href(step)}
              aria-current="step"
              className="flex items-center gap-2 pl-3.5 pr-4 py-2 rounded-full bg-primary-container text-on-primary shadow-pill-active"
            >
              <span className="w-2 h-2 rounded-full bg-secondary-container" />
              <span className="font-label-md text-label-md font-semibold tracking-tight">
                {step.number}. {step.label}
              </span>
              <Icon name="check_circle" className="text-[16px] text-secondary-container ml-0.5" />
            </Link>
          ) : (
            <Link
              key={step.slug}
              href={href(step)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-full text-on-surface-variant hover:text-on-surface hover:bg-surface-container/60 transition-colors"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-outline-variant" />
              <span className="font-label-md text-label-md">
                {step.number}. {step.label}
              </span>
            </Link>
          ),
        )}
      </div>
    </div>
  );
}
