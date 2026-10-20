import { Suspense } from "react";

import { BuildWorkspace } from "@/components/build/BuildWorkspace";

/** Step 9: Build & Export Power BI Project (design: dashpilot_step_9_build_export_power_bi_project). */
export default function BuildPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <BuildWorkspace />
    </Suspense>
  );
}
