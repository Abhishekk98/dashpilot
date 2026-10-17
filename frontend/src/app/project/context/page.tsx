import { Suspense } from "react";

import { ContextWorkspace } from "@/components/context/ContextWorkspace";

/** Step 3: Business Context & Brand Kit (design: dashpilot_step_3_business_context). */
export default function ContextPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <ContextWorkspace />
    </Suspense>
  );
}
