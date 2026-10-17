"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DashPilotLogo } from "@/components/brand/DashPilotLogo";
import { Icon } from "@/components/ui/Icon";
import { IconButton } from "@/components/ui/IconButton";
import { MAIN_NAV, isNavActive } from "@/lib/nav";

const NAV_BASE =
  "px-5 py-2 rounded-full font-body-md text-body-md transition-all duration-200";
const NAV_IDLE = "text-on-surface-variant hover:bg-surface-container hover:text-on-surface";
const NAV_ACTIVE =
  "bg-primary-container text-on-primary font-medium shadow-pill-active";

/** Floating pill header shared by every screen (matches the Stitch header markup). */
export function TopNav() {
  const pathname = usePathname();

  return (
    // Sticky inside the canvas; the canvas-coloured band behind the pill hides content
    // scrolling underneath, so nothing shows above or through the header.
    <header className="sticky top-0 z-50 w-full px-4 md:px-8 pt-3 md:pt-4 pb-3 bg-linear-to-b from-canvas from-75% to-canvas/0 print:hidden">
      <div className="h-20 w-full px-4 md:px-6 rounded-full bg-surface-container-lowest/80 backdrop-blur-xl shadow-nav flex items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-surface-container-low">
            <DashPilotLogo />
            <span className="font-title-lg text-title-lg tracking-tight text-on-surface font-semibold">DashPilot</span>
          </div>
        </Link>

        <nav className="hidden lg:flex items-center p-1.5 rounded-full bg-surface-container-low">
          {MAIN_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`${NAV_BASE} ${isNavActive(item.href, pathname) ? NAV_ACTIVE : NAV_IDLE}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2.5">
          <Link
            href="/settings"
            className="hidden sm:flex items-center gap-2 px-4 py-2 rounded-full font-body-md text-body-md bg-surface-container-low text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-all duration-200"
          >
            <Icon name="settings" className="text-[18px]" />
            <span>Settings</span>
          </Link>
          <IconButton icon="notifications" label="Notifications" variant="surface">
            <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-sunflower ring-2 ring-surface-container-lowest" />
          </IconButton>
          <div className="flex items-center pl-1">
            {/* Placeholder avatar until auth/user profiles exist. */}
            <button
              aria-label="Profile"
              type="button"
              className="w-10 h-10 rounded-full ring-2 ring-surface-container-lowest/70 bg-primary-container text-on-primary font-label-md text-label-md flex items-center justify-center hover:opacity-90 transition-opacity"
            >
              DP
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
