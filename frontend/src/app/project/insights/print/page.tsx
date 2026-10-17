import { Suspense } from "react";

import { InsightsPrint } from "@/components/insights/InsightsPrint";

/** Print-ready insights summary; "Save as PDF" from the browser's print dialog. */
export default function InsightsPrintPage() {
  return (
    <Suspense>
      <InsightsPrint />
    </Suspense>
  );
}
