import { Suspense } from "react";

import { InsightsWorkspace } from "@/components/insights/InsightsWorkspace";

/** Step 6: AI Insights & Narratives (design: dashpilot_step_6_ai_insights_narratives). */
export default function InsightsPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <InsightsWorkspace />
    </Suspense>
  );
}
