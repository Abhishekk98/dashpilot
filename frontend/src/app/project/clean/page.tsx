import { Suspense } from "react";

import { CleanWorkspace } from "@/components/clean/CleanWorkspace";

/** Step 2: Clean Data (design: dashpilot_step_2_clean_data). */
export default function CleanPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <CleanWorkspace />
    </Suspense>
  );
}
