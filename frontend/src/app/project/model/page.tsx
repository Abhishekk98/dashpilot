import { Suspense } from "react";

import { ModelWorkspace } from "@/components/model/ModelWorkspace";

/** Step 4: Data Model & Relationships (design: dashpilot_step_4_data_model_relationships). */
export default function ModelPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <ModelWorkspace />
    </Suspense>
  );
}
