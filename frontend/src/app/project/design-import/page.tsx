import { Suspense } from "react";

import { ImportWorkspace } from "@/components/import/ImportWorkspace";

/** Step 8: Import Design & Visual Mapping (design: dashpilot_step_8_import_design_visual_mapping). */
export default function DesignImportPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <ImportWorkspace />
    </Suspense>
  );
}
