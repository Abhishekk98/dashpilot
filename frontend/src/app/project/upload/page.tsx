import { Suspense } from "react";

import { UploadWorkspace } from "@/components/upload/UploadWorkspace";

/** Step 1: Upload & Profiling (design: dashpilot_new_project_upload_profiling). */
export default function UploadPage() {
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense>
      <UploadWorkspace />
    </Suspense>
  );
}
