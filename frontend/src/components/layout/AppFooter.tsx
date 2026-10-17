"use client";

import { useEffect, useState } from "react";

import { fetchHealth } from "@/lib/api";

type BackendState = "checking" | "online" | "offline";

const STATUS_TEXT: Record<BackendState, string> = {
  checking: "System Status: Checking…",
  online: "System Status: Normal",
  offline: "System Status: API Offline",
};

/** Footer strip from the designs; the status item reflects the live /api/health check. */
export function AppFooter() {
  const [state, setState] = useState<BackendState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(() => setState("online"))
      .catch((err) => {
        if (!controller.signal.aborted) {
          console.warn("Backend health check failed", err);
          setState("offline");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <footer className="w-full px-8 py-6 relative z-10 flex flex-col sm:flex-row items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-secondary-container" />
        <span className="font-label-md text-label-md text-on-surface-variant">
          DashPilot Workspace • Power BI Engine Active
        </span>
      </div>
      <div className="flex items-center gap-6 font-label-md text-label-md text-on-surface-variant">
        <span className="hover:text-on-surface cursor-pointer transition-colors">Security Enclave</span>
        <span className="hover:text-on-surface cursor-pointer transition-colors">DAX Semantic Layer</span>
        <span
          data-testid="system-status"
          className={`hover:text-on-surface cursor-pointer transition-colors ${state === "offline" ? "text-coral" : ""}`}
        >
          {STATUS_TEXT[state]}
        </span>
      </div>
    </footer>
  );
}
