import { notFound } from "next/navigation";

import { StepHeader } from "@/components/layout/StepHeader";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import { PIPELINE_STEPS, findStep } from "@/lib/steps";

export const dynamicParams = false;

// Steps with their own route folder (e.g. /project/upload) are excluded here.
const BUILT_STEPS = new Set(["upload", "clean", "context", "model", "kpis", "insights", "design-method"]);

export function generateStaticParams() {
  return PIPELINE_STEPS.filter((s) => !BUILT_STEPS.has(s.slug)).map((s) => ({ step: s.slug }));
}

/** Wizard step page. Each step's real UI replaces the placeholder in its own build step. */
export default async function StepPage({
  params,
  searchParams,
}: {
  params: Promise<{ step: string }>;
  searchParams: Promise<{ project?: string }>;
}) {
  const { step: slug } = await params;
  const { project } = await searchParams;
  const step = findStep(slug);
  if (!step) notFound();

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={step.number} title={step.title} projectId={project} />
      <PlaceholderCard
        icon="construction"
        title={`Step ${step.number}: ${step.title}`}
        description="This step's screen will be built to match its Stitch design."
      />
    </div>
  );
}
