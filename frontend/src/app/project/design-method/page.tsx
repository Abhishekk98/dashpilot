import { Suspense } from "react";

import { DesignWorkspace } from "@/components/design/DesignWorkspace";

/** Step 7: Dashboard plan + design method (B = DashPilot AI; A and C come later). */
export default function DesignMethodPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <DesignWorkspace />
    </Suspense>
  );
}
