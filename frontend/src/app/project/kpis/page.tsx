import { Suspense } from "react";

import { KpisWorkspace } from "@/components/kpis/KpisWorkspace";

/** Step 5: KPIs & DAX Formula Studio (design: dashpilot_step_5_kpis_dax_formulas). */
export default function KpisPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <KpisWorkspace />
    </Suspense>
  );
}
