/** Option lists for the Context step. Values mirror backend/core/context.py (the API rejects others). */

import type { Archetype, BrandPalette } from "./api";

export const INDUSTRIES = [
  "Retail", "Food Delivery", "E-commerce", "Finance & FinTech", "HR & People", "Healthcare",
  "SaaS & Subscription", "Manufacturing", "Logistics & Fleet", "Education", "Marketing Ops",
];

export const AUDIENCES: { label: string; icon: string }[] = [
  { label: "Executive Leadership", icon: "monitoring" },
  { label: "Sales Teams", icon: "handshake" },
  { label: "Growth Marketing", icon: "campaign" },
  { label: "Operations & Dispatch", icon: "hub" },
  { label: "Financial Controllers", icon: "account_balance" },
  { label: "Product Managers", icon: "deployed_code" },
];

export const FONT_STACKS: { label: string; note: string }[] = [
  { label: "Outfit + Inter", note: "JetBrains Mono Metrics" },
  { label: "Segoe UI", note: "Power BI default" },
  { label: "Inter", note: "Neutral sans" },
  { label: "Georgia + Segoe UI", note: "Editorial serif headers" },
];

export const SWATCHES: { key: keyof BrandPalette; label: string }[] = [
  { key: "accent", label: "Accent" },
  { key: "base", label: "Base" },
  { key: "muted", label: "Muted" },
  { key: "canvas", label: "Canvas" },
  { key: "growth", label: "Growth" },
];

/** Archetype cards; `preview` holds the miniature canvas colours from the design export. */
export const ARCHETYPES: {
  id: Archetype;
  title: string;
  tag: string;
  description: string;
  footer: string;
  preview: { canvas: string; bar: string; dot: string; tiles: [string, string, string]; strip: string };
}[] = [
  {
    id: "dark_futuristic",
    title: "Dark Futuristic",
    tag: "OLED",
    description: "Obsidian surface, luminous cyber-accents, telemetry focus.",
    footer: "High Contrast",
    preview: { canvas: "bg-[#111215]", bar: "bg-[#F8CF4B]/60", dot: "bg-cyan-400", tiles: ["bg-white/10", "bg-white/10", "bg-cyan-500/20"], strip: "bg-white/5" },
  },
  {
    id: "light_elegant",
    title: "Light Elegant",
    tag: "Nordic",
    description: "Airy warm canvas, charcoal headers, refined editorial spacing.",
    footer: "Executive Default",
    preview: { canvas: "bg-[#EEEEEC]", bar: "bg-[#232323]", dot: "bg-[#F8CF4B]", tiles: ["bg-white shadow-xs", "bg-white shadow-xs", "bg-[#F8CF4B]/40"], strip: "bg-white shadow-xs" },
  },
  {
    id: "glassmorphism",
    title: "Glassmorphism",
    tag: "Frosted",
    description: "Multi-depth frosted layers, ambient diffusion, tactile glass cards.",
    footer: "Modern macOS",
    preview: { canvas: "bg-gradient-to-br from-[#E3E2E2] to-[#FBF1CF]", bar: "bg-white/70", dot: "bg-amber-400", tiles: ["bg-white/50", "bg-white/60", "bg-white/40"], strip: "bg-white/40" },
  },
  {
    id: "minimal_corporate",
    title: "Minimal Corporate",
    tag: "Clean",
    description: "High information density, disciplined grids, tabular precision.",
    footer: "Enterprise Ready",
    preview: { canvas: "bg-white", bar: "bg-[#4F5665]", dot: "bg-blue-500", tiles: ["bg-[#F5F3F3]", "bg-[#F5F3F3]", "bg-[#F5F3F3]"], strip: "bg-[#E9E8E8]" },
  },
  {
    id: "neon_tech",
    title: "Neon Tech",
    tag: "Dense",
    description: "Vibrant metrics, sparklines, dark slate dashboard matrix.",
    footer: "DevOps & Telemetry",
    preview: { canvas: "bg-[#1A1C20]", bar: "bg-emerald-400", dot: "bg-[#F8CF4B]", tiles: ["bg-emerald-950/40", "bg-white/5", "bg-yellow-950/40"], strip: "bg-emerald-500/20" },
  },
];
