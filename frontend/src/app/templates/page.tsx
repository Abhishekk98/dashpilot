"use client";

import { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";

interface TemplateItem {
  id: string;
  name: string;
  category: "executive" | "operational" | "analytical";
  archetype: "Dark Futuristic" | "Light Elegant" | "Glassmorphism";
  layoutName: string;
  description: string;
  accent: string;
  canvasBg: string;
  cardBg: string;
  textColor: string;
  visualsRecommended: string;
  bestFor: string;
  wireframeLayout: "bento" | "hero_trend" | "side_panel" | "command_center" | "split";
}

const TEMPLATES: TemplateItem[] = [
  {
    id: "dark-bento",
    name: "Dark Futuristic Bento",
    category: "analytical",
    archetype: "Dark Futuristic",
    layoutName: "Bento Grid",
    description: "Sleek dark canvas with high-contrast sunflower yellow accents, glassmorphic cards, and high-density metric density.",
    accent: "#F8CF4B",
    canvasBg: "#111215",
    cardBg: "#1B1C20",
    textColor: "#F2F0F0",
    visualsRecommended: "6 - 10 Visuals",
    bestFor: "SaaS ARR, DevOps, Real-Time Fleet & Logistics Monitoring",
    wireframeLayout: "bento",
  },
  {
    id: "light-hero",
    name: "Light Elegant Executive",
    category: "executive",
    archetype: "Light Elegant",
    layoutName: "Hero KPI + Trend",
    description: "Nordic analytical eggshell canvas with prominent KPI callouts and a sweeping hero trend visual across the upper focal area.",
    accent: "#4CAF7A",
    canvasBg: "#FAF9F9",
    cardBg: "#FFFFFF",
    textColor: "#1B1C1C",
    visualsRecommended: "5 - 8 Visuals",
    bestFor: "Boardroom Presentations, CFO Dashboards, Quarterly Business Reviews",
    wireframeLayout: "hero_trend",
  },
  {
    id: "glass-sidepanel",
    name: "Glassmorphic Operations",
    category: "operational",
    archetype: "Glassmorphism",
    layoutName: "Side Panel Rail",
    description: "Left vertical navigation and slicer rail with a clean 2x2 multi-card workspace for deep slice-and-dice workflows.",
    accent: "#3B82F6",
    canvasBg: "#F4F1EA",
    cardBg: "#FFFFFF",
    textColor: "#232323",
    visualsRecommended: "7 - 12 Visuals",
    bestFor: "E-Commerce Fulfillment, Swiggy/Zomato Delivery Pulse, Inventory Tracking",
    wireframeLayout: "side_panel",
  },
  {
    id: "command-center",
    name: "High-Throughput Command Center",
    category: "operational",
    archetype: "Dark Futuristic",
    layoutName: "Command Center",
    description: "Dense 3-column operations dashboard with top KPI telemetry band and full-bleed Key Insights narrative sidebar.",
    accent: "#F59E0B",
    canvasBg: "#0D0E11",
    cardBg: "#16181D",
    textColor: "#FFFFFF",
    visualsRecommended: "8 - 14 Visuals",
    bestFor: "Healthcare Emergency Occupancy, Network Operations (NOC), Fraud Detection",
    wireframeLayout: "command_center",
  },
  {
    id: "executive-split",
    name: "Comparative Executive Split",
    category: "executive",
    archetype: "Light Elegant",
    layoutName: "Executive Split",
    description: "Balanced 50/50 dual-section layout designed for Year-over-Year, Target vs Actual, and Regional comparative analysis.",
    accent: "#6366F1",
    canvasBg: "#FAFAFA",
    cardBg: "#FFFFFF",
    textColor: "#18181B",
    visualsRecommended: "6 - 8 Visuals",
    bestFor: "Retail Budget vs Actuals, Marketing Campaign Cohorts, Sales Pipeline",
    wireframeLayout: "split",
  },
];

export default function TemplatesPage() {
  const [activeCategory, setActiveCategory] = useState<"all" | "executive" | "operational" | "analytical">("all");
  const [previewTemplate, setPreviewTemplate] = useState<TemplateItem | null>(null);

  const filtered = TEMPLATES.filter((t) => activeCategory === "all" || t.category === activeCategory);

  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* Header */}
      <section className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-6 border-b border-outline-variant/30">
        <div>
          <span className="font-label-sm text-label-sm text-secondary uppercase tracking-widest font-semibold flex items-center gap-1.5 mb-2">
            <Icon name="dashboard_customize" size={14} />
            Architectural Layout Library
          </span>
          <h1 className="font-display-lg text-display-lg text-primary tracking-tight font-medium">
            Dashboard Templates
          </h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-1.5 font-light">
            Engineered Power BI layouts strictly aligned to 1280×720 canvas dimensions with native slicers, KPI hero rows, and action button navigation.
          </p>
        </div>

        <PillButton href="/project/upload" arrow>
          Start with Template
        </PillButton>
      </section>

      {/* Categories Filter Tabs */}
      <div className="flex items-center p-1 rounded-full bg-surface-container-low border border-outline-variant/20 self-start">
        <button
          onClick={() => setActiveCategory("all")}
          className={`px-4 py-1.5 rounded-full text-[12px] font-medium transition-all ${
            activeCategory === "all"
              ? "bg-surface-container-lowest text-primary shadow-xs"
              : "text-on-surface-variant hover:text-primary"
          }`}
        >
          All Templates ({TEMPLATES.length})
        </button>
        <button
          onClick={() => setActiveCategory("executive")}
          className={`px-4 py-1.5 rounded-full text-[12px] font-medium transition-all ${
            activeCategory === "executive"
              ? "bg-surface-container-lowest text-primary shadow-xs"
              : "text-on-surface-variant hover:text-primary"
          }`}
        >
          Executive
        </button>
        <button
          onClick={() => setActiveCategory("operational")}
          className={`px-4 py-1.5 rounded-full text-[12px] font-medium transition-all ${
            activeCategory === "operational"
              ? "bg-surface-container-lowest text-primary shadow-xs"
              : "text-on-surface-variant hover:text-primary"
          }`}
        >
          Operational
        </button>
        <button
          onClick={() => setActiveCategory("analytical")}
          className={`px-4 py-1.5 rounded-full text-[12px] font-medium transition-all ${
            activeCategory === "analytical"
              ? "bg-surface-container-lowest text-primary shadow-xs"
              : "text-on-surface-variant hover:text-primary"
          }`}
        >
          Analytical
        </button>
      </div>

      {/* Templates Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filtered.map((tmpl) => (
          <div
            key={tmpl.id}
            className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card hover:shadow-card-hover transition-all duration-300 border border-outline-variant/20 flex flex-col justify-between group"
          >
            <div>
              {/* Mini Wireframe Preview */}
              <div
                className="h-44 rounded-2xl p-3.5 mb-5 flex flex-col justify-between relative overflow-hidden transition-transform duration-300 group-hover:scale-[1.01]"
                style={{ backgroundColor: tmpl.canvasBg, border: "1px solid rgba(0,0,0,0.08)" }}
              >
                {/* Header Wireframe */}
                <div className="flex items-center justify-between pb-2 border-b border-white/10">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-3.5 h-3.5 rounded-md flex items-center justify-center text-[8px] font-bold"
                      style={{ backgroundColor: tmpl.accent, color: "#111" }}
                    >
                      D
                    </span>
                    <span className="w-16 h-2 rounded bg-white/20" />
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="w-8 h-2.5 rounded-full bg-white/15" />
                    <span className="w-8 h-2.5 rounded-full bg-white/15" />
                    <span
                      className="w-8 h-2.5 rounded-full text-[7px] flex items-center justify-center font-bold"
                      style={{ backgroundColor: tmpl.accent, color: "#111" }}
                    >
                      NAV
                    </span>
                  </div>
                </div>

                {/* Layout Specific Visuals Wireframe */}
                {tmpl.wireframeLayout === "bento" && (
                  <div className="grid grid-cols-3 gap-2 flex-1 pt-2">
                    <div className="col-span-3 h-5 rounded-lg bg-white/10 flex gap-1.5 px-2 items-center">
                      <span className="w-10 h-2 rounded bg-white/25" />
                      <span className="w-10 h-2 rounded bg-white/25" />
                      <span className="w-10 h-2 rounded bg-white/25" />
                    </div>
                    <div className="col-span-2 rounded-xl bg-white/15 p-2 flex flex-col justify-end">
                      <span className="w-full h-8 rounded bg-white/20" />
                    </div>
                    <div className="col-span-1 rounded-xl bg-white/10 p-2 flex flex-col justify-between">
                      <span className="w-full h-6 rounded bg-white/15" />
                      <span className="w-full h-6 rounded bg-white/15" />
                    </div>
                  </div>
                )}

                {tmpl.wireframeLayout === "hero_trend" && (
                  <div className="flex flex-col gap-2 flex-1 pt-2">
                    <div className="h-14 rounded-xl bg-white/15 p-2 flex items-end">
                      <span className="w-full h-7 rounded bg-white/20" />
                    </div>
                    <div className="grid grid-cols-3 gap-2 flex-1">
                      <div className="rounded-lg bg-white/10" />
                      <div className="rounded-lg bg-white/10" />
                      <div className="rounded-lg bg-white/10" />
                    </div>
                  </div>
                )}

                {tmpl.wireframeLayout === "side_panel" && (
                  <div className="grid grid-cols-4 gap-2 flex-1 pt-2">
                    <div className="col-span-1 rounded-xl bg-white/15 p-2 flex flex-col gap-1.5">
                      <span className="w-full h-3 rounded bg-white/20" />
                      <span className="w-full h-3 rounded bg-white/20" />
                      <span className="w-full h-3 rounded bg-white/20" />
                    </div>
                    <div className="col-span-3 grid grid-cols-2 gap-2">
                      <div className="rounded-xl bg-white/10" />
                      <div className="rounded-xl bg-white/10" />
                      <div className="rounded-xl bg-white/10" />
                      <div className="rounded-xl bg-white/10" />
                    </div>
                  </div>
                )}

                {tmpl.wireframeLayout === "command_center" && (
                  <div className="grid grid-cols-3 gap-2 flex-1 pt-2">
                    <div className="col-span-3 h-4 rounded bg-white/10" />
                    <div className="col-span-2 rounded-xl bg-white/15" />
                    <div
                      className="col-span-1 rounded-xl p-1.5"
                      style={{ borderLeft: `2px solid ${tmpl.accent}`, backgroundColor: "rgba(255,255,255,0.08)" }}
                    />
                  </div>
                )}

                {tmpl.wireframeLayout === "split" && (
                  <div className="grid grid-cols-2 gap-2 flex-1 pt-2">
                    <div className="rounded-xl bg-white/15 p-2 flex flex-col justify-between">
                      <span className="w-12 h-2 rounded bg-white/25" />
                      <span className="w-full h-10 rounded bg-white/20" />
                    </div>
                    <div className="rounded-xl bg-white/15 p-2 flex flex-col justify-between">
                      <span className="w-12 h-2 rounded bg-white/25" />
                      <span className="w-full h-10 rounded bg-white/20" />
                    </div>
                  </div>
                )}

                {/* Bottom Tag */}
                <div className="flex items-center justify-between pt-1">
                  <span
                    className="text-[9px] uppercase tracking-wider font-bold"
                    style={{ color: tmpl.accent }}
                  >
                    {tmpl.layoutName}
                  </span>
                  <span className="text-[9px] text-white/60 font-mono">1280 × 720</span>
                </div>
              </div>

              {/* Title & Archetype Badges */}
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
                  {tmpl.archetype}
                </span>
                <span className="text-[11px] font-mono text-on-surface-variant font-medium">
                  {tmpl.visualsRecommended}
                </span>
              </div>

              <h3 className="font-headline-md text-headline-md font-semibold text-primary mb-2">
                {tmpl.name}
              </h3>

              <p className="text-[12px] text-on-surface-variant mb-4 leading-relaxed line-clamp-2">
                {tmpl.description}
              </p>

              {/* Specs Box */}
              <div className="p-3 rounded-2xl bg-surface-container-low/70 mb-5 border border-outline-variant/15 text-[11px]">
                <span className="text-[10px] uppercase font-semibold text-on-surface-variant block mb-1">
                  OPTIMAL USE CASE
                </span>
                <span className="text-primary font-medium block truncate">
                  {tmpl.bestFor}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between gap-2 pt-3 border-t border-outline-variant/15">
              <button
                type="button"
                onClick={() => setPreviewTemplate(tmpl)}
                className="text-[12px] font-medium text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1"
              >
                <Icon name="visibility" size={16} />
                <span>Specs</span>
              </button>

              <Link
                href="/project/upload"
                className="px-4 py-1.5 rounded-full bg-primary text-on-primary hover:opacity-95 transition-all text-[12px] font-medium flex items-center gap-1 shadow-2xs"
              >
                <span>Use Layout</span>
                <Icon name="arrow_forward" size={14} />
              </Link>
            </div>
          </div>
        ))}
      </div>

      {/* Specs Detail Modal */}
      {previewTemplate && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-surface-container-lowest rounded-[32px] p-8 max-w-lg w-full shadow-2xl border border-outline-variant/30 flex flex-col gap-6 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[11px] font-semibold text-secondary uppercase tracking-widest block mb-1">
                  {previewTemplate.archetype} · {previewTemplate.layoutName}
                </span>
                <h2 className="font-headline-lg text-headline-lg font-bold text-primary">
                  {previewTemplate.name}
                </h2>
              </div>
              <button
                onClick={() => setPreviewTemplate(null)}
                className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary"
              >
                ×
              </button>
            </div>

            <p className="text-[13px] text-on-surface-variant leading-relaxed">
              {previewTemplate.description}
            </p>

            <div className="space-y-3 bg-surface-container-low/70 p-4 rounded-2xl border border-outline-variant/20 text-[12px]">
              <div className="flex justify-between py-1 border-b border-outline-variant/15">
                <span className="text-on-surface-variant font-medium">Grid Resolution</span>
                <span className="font-mono font-semibold text-primary">1280 × 720 (16:9)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-outline-variant/15">
                <span className="text-on-surface-variant font-medium">Recommended Density</span>
                <span className="font-medium text-primary">{previewTemplate.visualsRecommended}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-outline-variant/15">
                <span className="text-on-surface-variant font-medium">Accent Hex</span>
                <span className="font-mono font-semibold text-primary">{previewTemplate.accent}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-on-surface-variant font-medium">Best For</span>
                <span className="font-medium text-primary text-right max-w-xs">{previewTemplate.bestFor}</span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setPreviewTemplate(null)}
                className="px-5 py-2.5 rounded-full text-on-surface-variant hover:text-primary font-medium text-[13px]"
              >
                Close
              </button>
              <PillButton href="/project/upload" arrow>
                Apply to New Project
              </PillButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
