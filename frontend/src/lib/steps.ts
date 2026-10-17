/** The 9-step DashPilot pipeline, in the order shown in the stepper ribbon. */
export interface PipelineStep {
  number: number;
  slug: string;
  label: string;
  /** Title used for the step page heading. */
  title: string;
}

export const PIPELINE_STEPS: PipelineStep[] = [
  { number: 1, slug: "upload", label: "Upload", title: "Upload & Profiling" },
  { number: 2, slug: "clean", label: "Clean", title: "Clean Data" },
  { number: 3, slug: "context", label: "Context", title: "Business Context" },
  { number: 4, slug: "model", label: "Model", title: "Data Model & Relationships" },
  { number: 5, slug: "kpis", label: "KPIs & DAX", title: "KPIs & DAX Formulas" },
  { number: 6, slug: "insights", label: "Insights", title: "AI Insights & Narratives" },
  { number: 7, slug: "design-method", label: "Design Method", title: "Choose Design Method" },
  { number: 8, slug: "design-import", label: "Design Import", title: "Import Design & Visual Mapping" },
  { number: 9, slug: "build", label: "Build", title: "Build & Export Power BI Project" },
];

export function stepHref(step: PipelineStep): string {
  return `/project/${step.slug}`;
}

export function findStep(slug: string): PipelineStep | undefined {
  return PIPELINE_STEPS.find((s) => s.slug === slug);
}
