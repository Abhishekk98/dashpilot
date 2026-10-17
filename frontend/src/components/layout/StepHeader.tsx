import Link from "next/link";
import type { ReactNode } from "react";

import { Icon } from "@/components/ui/Icon";
import { PillTag } from "@/components/ui/PillTag";
import { StepTracker } from "@/components/ui/StepTracker";

interface StepHeaderProps {
  step: number;
  title: string;
  projectId?: string | null;
  /** Small pill shown next to the title, e.g. "Draft". */
  badge?: string;
  /** Right-hand status content (engine pill, menu). */
  status?: ReactNode;
}

/** "Top Navigation & Flow Orchestration Header" shared by the 9 workflow screens. */
export function StepHeader({ step, title, projectId, badge, status }: StepHeaderProps) {
  return (
    <section className="flex flex-col gap-6 mb-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            aria-label="Back to Home"
            className="w-10 h-10 rounded-full bg-surface-container-lowest/80 backdrop-blur-xl flex items-center justify-center text-on-surface hover:bg-surface-container transition-all shadow-[0_8px_24px_-4px_rgba(35,35,35,0.04)]"
          >
            <Icon name="arrow_back" className="text-[20px]" />
          </Link>
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-body-md text-body-md text-on-surface-variant shrink-0">New Project</span>
            <span className="text-outline-variant font-code-sm">/</span>
            <h1 className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight truncate">
              {title}
            </h1>
            {badge && (
              <PillTag className="ml-1">{badge}</PillTag>
            )}
          </div>
        </div>
        {status && <div className="flex items-center gap-2">{status}</div>}
      </div>
      <StepTracker currentStep={step} projectId={projectId} />
    </section>
  );
}
