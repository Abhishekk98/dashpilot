import type { ReactNode } from "react";

import { AppFooter } from "./AppFooter";
import { TopNav } from "./TopNav";

/**
 * Outer frame shared by every screen: slate shell, rounded canvas with the
 * sunflower glow, sticky floating header, main area and footer.
 *
 * overflow-clip (not overflow-hidden) keeps the rounded corners without turning
 * the canvas into a scroll container, which would break the sticky header.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[1440px] mx-auto min-h-[calc(100vh-4rem)] rounded-none md:rounded-canvas bg-canvas bg-canvas-glow shadow-canvas relative overflow-clip flex flex-col justify-between">
      <TopNav />
      {/* The header is sticky and in the flow, so main only needs a small top gap. */}
      <main className="w-full pt-4 px-6 lg:px-10 pb-12 flex-1 relative z-10 flex flex-col">{children}</main>
      <AppFooter />
    </div>
  );
}
