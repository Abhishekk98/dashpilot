"use client";

import { useState, useMemo, useEffect } from "react";
import { Icon } from "@/components/ui/Icon";

interface BrandKit {
  id: string;
  name: string;
  category: "Nordic Minimal" | "Executive Dark" | "Modern Retail" | "Industrial" | "High Tech";
  tagline: string;
  description: string;
  isCustom?: boolean;
  wcagLevel: "AAA" | "AA" | "AA Large";
  canvas: string;
  card: string;
  text: string;
  muted: string;
  accent: string;
  secondaryAccent: string;
  dataColors: string[];
  fonts: {
    display: string;
    body: string;
    metrics: string;
  };
  borderRadius: number;
}

const DEFAULT_BRAND_KITS: BrandKit[] = [
  {
    id: "nordic-default",
    name: "Nordic Analytical Canvas",
    category: "Nordic Minimal",
    tagline: "The default DashPilot studio aesthetic",
    description: "Warm off-white parchment canvas with deep charcoal ink and radiant sunflower yellow accents. Engineered for peak cognitive clarity in complex analytics.",
    wcagLevel: "AAA",
    canvas: "#FAF9F9",
    card: "#FFFFFF",
    text: "#1B1C1C",
    muted: "#6B6B6B",
    accent: "#F8CF4B",
    secondaryAccent: "#4CAF7A",
    dataColors: [
      "#F8CF4B",
      "#232323",
      "#4CAF7A",
      "#3B82F6",
      "#E06666",
      "#8B5CF6",
      "#F97316",
      "#06B6D4",
    ],
    fonts: {
      display: "Outfit",
      body: "Inter",
      metrics: "Segoe UI",
    },
    borderRadius: 24,
  },
  {
    id: "executive-obsidian",
    name: "Executive Obsidian",
    category: "Executive Dark",
    tagline: "Boardroom & CFO cockpit presentation",
    description: "Deep obsidian midnight background with cool slate surfaces and electric sky blue telemetry. High visual weight with zero eye fatigue in low light.",
    wcagLevel: "AAA",
    canvas: "#0F172A",
    card: "#1E293B",
    text: "#F8FAFC",
    muted: "#94A3B8",
    accent: "#38BDF8",
    secondaryAccent: "#10B981",
    dataColors: [
      "#38BDF8",
      "#818CF8",
      "#34D399",
      "#F472B6",
      "#FBBF24",
      "#A78BFA",
      "#60A5FA",
      "#2DD4BF",
    ],
    fonts: {
      display: "Plus Jakarta Sans",
      body: "Inter",
      metrics: "Segoe UI",
    },
    borderRadius: 20,
  },
  {
    id: "retail-emerald",
    name: "Emerald Commerce",
    category: "Modern Retail",
    tagline: "Omni-channel sales, inventory & margins",
    description: "Organic forest emerald and warm goldenrod tones. Inspires trust, stability, and growth while retaining strict separation between positive and negative variance.",
    wcagLevel: "AA",
    canvas: "#F4F7F4",
    card: "#FFFFFF",
    text: "#064E3B",
    muted: "#475569",
    accent: "#10B981",
    secondaryAccent: "#F59E0B",
    dataColors: [
      "#10B981",
      "#F59E0B",
      "#0284C7",
      "#8B5CF6",
      "#EC4899",
      "#14B8A6",
      "#EAB308",
      "#EF4444",
    ],
    fonts: {
      display: "Outfit",
      body: "Inter",
      metrics: "Segoe UI",
    },
    borderRadius: 16,
  },
  {
    id: "steel-logistics",
    name: "Steel Route & Telemetry",
    category: "Industrial",
    tagline: "Heavy supply chain, transport & dispatch",
    description: "High-contrast cool gray canvas with vivid cobalt and warning hazard orange. Built for fast scanning in bustling warehouse control rooms and flight operations.",
    wcagLevel: "AAA",
    canvas: "#F1F5F9",
    card: "#FFFFFF",
    text: "#0F172A",
    muted: "#64748B",
    accent: "#2563EB",
    secondaryAccent: "#EA580C",
    dataColors: [
      "#2563EB",
      "#EA580C",
      "#059669",
      "#7C3AED",
      "#0284C7",
      "#D97706",
      "#DC2626",
      "#475569",
    ],
    fonts: {
      display: "DM Sans",
      body: "Inter",
      metrics: "Segoe UI",
    },
    borderRadius: 14,
  },
  {
    id: "neon-cyber",
    name: "Cyber Neon AI",
    category: "High Tech",
    tagline: "Developer infrastructure & LLM benchmarking",
    description: "Pitch black void canvas with ultraviolet violet and radioactive teal. High-energy aesthetic for cutting-edge AI observability dashboards.",
    wcagLevel: "AA",
    canvas: "#0B0F19",
    card: "#131C2E",
    text: "#F1F5F9",
    muted: "#94A3B8",
    accent: "#8B5CF6",
    secondaryAccent: "#06B6D4",
    dataColors: [
      "#8B5CF6",
      "#06B6D4",
      "#EC4899",
      "#10B981",
      "#F59E0B",
      "#3B82F6",
      "#F43F5E",
      "#A855F7",
    ],
    fonts: {
      display: "Outfit",
      body: "Inter",
      metrics: "Segoe UI",
    },
    borderRadius: 24,
  },
];

// Helper to calculate relative luminance & contrast ratio
function getContrastRatio(hex1: string, hex2: string): number {
  const getLuminance = (hex: string) => {
    const clean = hex.replace("#", "");
    if (clean.length !== 6) return 0.5;
    const r = parseInt(clean.substring(0, 2), 16) / 255;
    const g = parseInt(clean.substring(2, 4), 16) / 255;
    const b = parseInt(clean.substring(4, 6), 16) / 255;
    const a = [r, g, b].map((v) =>
      v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
    );
    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
  };
  const lum1 = getLuminance(hex1);
  const lum2 = getLuminance(hex2);
  const brightest = Math.max(lum1, lum2);
  const darkest = Math.min(lum1, lum2);
  return (brightest + 0.05) / (darkest + 0.05);
}

export default function BrandKitsPage() {
  const [kits, setKits] = useState<BrandKit[]>(DEFAULT_BRAND_KITS);
  const [activeKitId, setActiveKitId] = useState<string>("nordic-default");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [copiedJson, setCopiedJson] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // Active Kit reference
  const activeKit = useMemo(() => {
    return kits.find((k) => k.id === activeKitId) || kits[0];
  }, [kits, activeKitId]);

  // Working edit state
  const [customKit, setCustomKit] = useState<BrandKit>(activeKit);

  useEffect(() => {
    setCustomKit(activeKit);
  }, [activeKit]);

  // Calculate contrast ratios
  const textVsCanvasRatio = useMemo(() => {
    return getContrastRatio(customKit.text, customKit.canvas).toFixed(1);
  }, [customKit.text, customKit.canvas]);

  const textVsCardRatio = useMemo(() => {
    return getContrastRatio(customKit.text, customKit.card).toFixed(1);
  }, [customKit.text, customKit.card]);

  const accentVsCardRatio = useMemo(() => {
    return getContrastRatio(customKit.accent, customKit.card).toFixed(1);
  }, [customKit.accent, customKit.card]);

  // Generate Power BI Theme JSON
  const themeJson = useMemo(() => {
    const pbiTheme = {
      name: `DashPilot ${customKit.name}`,
      dataColors: customKit.dataColors,
      background: customKit.canvas,
      foreground: customKit.text,
      tableAccent: customKit.accent,
      visualStyles: {
        "*": {
          "*": {
            outspace: [{ color: { solid: { color: customKit.canvas } } }],
            background: [{ show: false, color: { solid: { color: customKit.card } } }],
            border: [{ show: false }],
            dropShadow: [{ show: false }],
          },
        },
      },
      textClasses: {
        callout: {
          fontSize: 28,
          fontFace: customKit.fonts.display || "Segoe UI",
          color: customKit.text,
        },
        title: {
          fontSize: 16,
          fontFace: customKit.fonts.display || "Segoe UI",
          color: customKit.text,
        },
        header: {
          fontSize: 12,
          fontFace: customKit.fonts.body || "Segoe UI",
          color: customKit.muted,
        },
        label: {
          fontSize: 10,
          fontFace: customKit.fonts.body || "Segoe UI",
          color: customKit.muted,
        },
      },
    };
    return JSON.stringify(pbiTheme, null, 2);
  }, [customKit]);

  const handleCopyJson = () => {
    navigator.clipboard.writeText(themeJson);
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2200);
  };

  const handleDownloadJson = () => {
    const blob = new Blob([themeJson], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dashpilot-theme-${customKit.id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleSaveCustomKit = () => {
    const updatedKit: BrandKit = {
      ...customKit,
      id: customKit.isCustom ? customKit.id : `custom-${Date.now()}`,
      name: customKit.isCustom ? customKit.name : `${customKit.name} (Custom)`,
      isCustom: true,
    };
    const updatedList = kits.some((k) => k.id === updatedKit.id)
      ? kits.map((k) => (k.id === updatedKit.id ? updatedKit : k))
      : [updatedKit, ...kits];
    setKits(updatedList);
    setActiveKitId(updatedKit.id);
    setIsEditing(false);
  };

  const filteredKits = useMemo(() => {
    if (filterCategory === "all") return kits;
    return kits.filter((k) => k.category.toLowerCase().includes(filterCategory.toLowerCase()));
  }, [kits, filterCategory]);

  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* Top Banner & Header */}
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-sunflower/20 text-on-surface">
              <Icon name="palette" size={14} />
            </span>
            <span className="font-mono text-xs uppercase tracking-wider text-on-surface-variant">
              Design System Engine
            </span>
            <span className="rounded-full bg-surface-container-high px-2 py-0.5 text-[10px] font-semibold text-on-surface-variant">
              Power BI .pbip Compliant
            </span>
          </div>
          <h1 className="mt-1 font-title-lg text-2xl font-bold tracking-tight text-on-surface sm:text-3xl">
            Brand Kits & Color Architectures
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant max-w-3xl">
            Configure palettes, typography standards, and contrast metrics applied directly during DAX generation and Power BI template assembly.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={handleDownloadJson}
            className="flex items-center gap-1.5 rounded-full border border-outline-variant/60 bg-surface-container-lowest px-4 py-2 text-xs font-semibold text-on-surface shadow-sm transition-all hover:border-on-surface hover:bg-surface-container-low"
          >
            <Icon name="download" size={14} />
            Export Power BI Theme (.json)
          </button>
          <button
            onClick={() => {
              const newCustom: BrandKit = {
                id: `custom-${Date.now()}`,
                name: "New Custom Brand",
                category: "Nordic Minimal",
                tagline: "Custom corporate design profile",
                description: "User customized color palette with tailored primary and secondary contrast hierarchy.",
                isCustom: true,
                wcagLevel: "AAA",
                canvas: "#F8F9FA",
                card: "#FFFFFF",
                text: "#1E293B",
                muted: "#64748B",
                accent: "#6366F1",
                secondaryAccent: "#10B981",
                dataColors: ["#6366F1", "#10B981", "#F59E0B", "#EF4444", "#3B82F6", "#8B5CF6", "#14B8A6", "#64748B"],
                fonts: { display: "Outfit", body: "Inter", metrics: "Segoe UI" },
                borderRadius: 20,
              };
              setKits([newCustom, ...kits]);
              setActiveKitId(newCustom.id);
              setIsEditing(true);
            }}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-on-primary shadow-sm transition-all hover:bg-primary/90"
          >
            <Icon name="add" size={14} />
            Create Brand Kit
          </button>
        </div>
      </div>

      {/* Main Grid: Left Kit Selector + Right Live Preview & Customizer */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Left Column: Preset Kits & Filter (5 Cols) */}
        <div className="flex flex-col gap-5 lg:col-span-5">
          <div className="flex items-center justify-between">
            <h2 className="font-title-md text-base font-semibold text-on-surface">
              Design Systems ({kits.length})
            </h2>
            <div className="flex gap-1">
              {["all", "nordic", "executive", "retail", "tech"].map((cat) => (
                <button
                  key={cat}
                  onClick={() => setFilterCategory(cat)}
                  className={`rounded-full px-2.5 py-1 text-[11px] font-medium capitalize transition-all ${
                    filterCategory === cat
                      ? "bg-charcoal text-white font-semibold"
                      : "bg-surface-container-high text-on-surface-variant hover:text-on-surface"
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            {filteredKits.map((k) => {
              const isSelected = k.id === activeKitId;
              return (
                <div
                  key={k.id}
                  onClick={() => {
                    setActiveKitId(k.id);
                    setIsEditing(false);
                  }}
                  className={`group relative cursor-pointer rounded-2xl border p-4 transition-all duration-200 ${
                    isSelected
                      ? "border-primary bg-surface-container-lowest shadow-md ring-1 ring-primary/20"
                      : "border-outline-variant/40 bg-surface-container-low/60 hover:border-outline hover:bg-surface-container-lowest"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-title-sm text-sm font-bold text-on-surface">
                          {k.name}
                        </span>
                        {k.isCustom && (
                          <span className="rounded-full bg-secondary-fixed/50 px-2 py-0.5 text-[9px] font-bold text-on-surface">
                            Custom
                          </span>
                        )}
                        <span className="rounded-full bg-surface-container-high px-2 py-0.5 text-[9px] font-semibold text-on-surface-variant">
                          WCAG {k.wcagLevel}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-on-surface-variant line-clamp-1">
                        {k.tagline}
                      </p>
                    </div>

                    {isSelected && (
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-on-primary">
                        <Icon name="check" size={12} />
                      </span>
                    )}
                  </div>

                  {/* Palette Swatches Bar */}
                  <div className="mt-3.5 flex items-center gap-1.5">
                    {/* Primary Accent Circle */}
                    <div
                      className="h-6 w-6 rounded-full border border-black/10 shadow-inner flex items-center justify-center"
                      style={{ backgroundColor: k.accent }}
                      title={`Accent: ${k.accent}`}
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-white/70" />
                    </div>
                    {/* Canvas & Card Pill */}
                    <div
                      className="flex h-6 items-center gap-1 rounded-full border border-black/10 px-2 text-[10px] font-mono font-medium shadow-inner"
                      style={{ backgroundColor: k.canvas, color: k.text }}
                      title={`Canvas: ${k.canvas}`}
                    >
                      <span>Bg</span>
                    </div>
                    {/* Data color dots */}
                    <div className="ml-auto flex items-center -space-x-1">
                      {k.dataColors.slice(0, 6).map((dc, i) => (
                        <div
                          key={i}
                          className="h-4 w-4 rounded-full border border-white shadow-sm"
                          style={{ backgroundColor: dc }}
                          title={`Color ${i + 1}: ${dc}`}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Quick Info Box */}
          <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-4 text-xs text-on-surface-variant flex flex-col gap-2">
            <div className="flex items-center gap-2 font-semibold text-on-surface">
              <Icon name="info" size={16} />
              <span>How DashPilot Uses Brand Kits</span>
            </div>
            <p className="leading-relaxed">
              When DashPilot generates <code>Report.json</code> and compiles the <code>.pbip</code> archive, it injects these tokens into the <code>StaticResources/RegisteredResources/DashPilotTheme.json</code> file. Visuals automatically adhere to data color order, contrast ratios, and header typography.
            </p>
          </div>
        </div>

        {/* Right Column: Live Interactive Dashboard Studio (7 Cols) */}
        <div className="flex flex-col gap-6 lg:col-span-7">
          {/* Header Controls for Active Kit */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-4">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-title-md text-lg font-bold text-on-surface">
                  {customKit.name}
                </h3>
                <span className="rounded-full bg-surface-container px-2 py-0.5 text-[10px] font-medium text-on-surface-variant">
                  {customKit.category}
                </span>
              </div>
              <p className="text-xs text-on-surface-variant mt-0.5">
                {customKit.description}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsEditing(!isEditing)}
                className={`flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                  isEditing
                    ? "bg-charcoal text-white"
                    : "border border-outline-variant/60 bg-surface hover:bg-surface-container"
                }`}
              >
                <Icon name={isEditing ? "close" : "edit"} size={13} />
                {isEditing ? "Close Editor" : "Customize Swatches"}
              </button>
              {isEditing && (
                <button
                  onClick={handleSaveCustomKit}
                  className="flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-on-primary hover:bg-primary/90"
                >
                  <Icon name="check" size={13} />
                  Save Kit
                </button>
              )}
            </div>
          </div>

          {/* Color & Typography Customizer Panel (Visible when editing) */}
          {isEditing && (
            <div className="rounded-2xl border border-outline-variant/50 bg-surface-container-lowest p-5 flex flex-col gap-4 animate-in fade-in duration-200">
              <div className="flex items-center justify-between border-b border-outline-variant/20 pb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-on-surface">
                  Interactive Palette Adjustments
                </span>
                <span className="text-[11px] text-on-surface-variant">
                  Updates reflect instantly in the live mockup below
                </span>
              </div>

              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                {/* Accent Picker */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-[11px] font-semibold text-on-surface-variant">
                    Primary Accent
                  </label>
                  <div className="flex items-center gap-2 rounded-lg border border-outline-variant/60 bg-surface-container-low px-2 py-1">
                    <input
                      type="color"
                      value={customKit.accent}
                      onChange={(e) => setCustomKit({ ...customKit, accent: e.target.value })}
                      className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent"
                    />
                    <input
                      type="text"
                      value={customKit.accent}
                      onChange={(e) => setCustomKit({ ...customKit, accent: e.target.value })}
                      className="w-full bg-transparent font-mono text-xs uppercase text-on-surface focus:outline-none"
                    />
                  </div>
                </div>

                {/* Canvas Bg Picker */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-[11px] font-semibold text-on-surface-variant">
                    Canvas Bg
                  </label>
                  <div className="flex items-center gap-2 rounded-lg border border-outline-variant/60 bg-surface-container-low px-2 py-1">
                    <input
                      type="color"
                      value={customKit.canvas}
                      onChange={(e) => setCustomKit({ ...customKit, canvas: e.target.value })}
                      className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent"
                    />
                    <input
                      type="text"
                      value={customKit.canvas}
                      onChange={(e) => setCustomKit({ ...customKit, canvas: e.target.value })}
                      className="w-full bg-transparent font-mono text-xs uppercase text-on-surface focus:outline-none"
                    />
                  </div>
                </div>

                {/* Card Bg Picker */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-[11px] font-semibold text-on-surface-variant">
                    Card Surface
                  </label>
                  <div className="flex items-center gap-2 rounded-lg border border-outline-variant/60 bg-surface-container-low px-2 py-1">
                    <input
                      type="color"
                      value={customKit.card}
                      onChange={(e) => setCustomKit({ ...customKit, card: e.target.value })}
                      className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent"
                    />
                    <input
                      type="text"
                      value={customKit.card}
                      onChange={(e) => setCustomKit({ ...customKit, card: e.target.value })}
                      className="w-full bg-transparent font-mono text-xs uppercase text-on-surface focus:outline-none"
                    />
                  </div>
                </div>

                {/* Primary Text Picker */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-[11px] font-semibold text-on-surface-variant">
                    Ink / Text
                  </label>
                  <div className="flex items-center gap-2 rounded-lg border border-outline-variant/60 bg-surface-container-low px-2 py-1">
                    <input
                      type="color"
                      value={customKit.text}
                      onChange={(e) => setCustomKit({ ...customKit, text: e.target.value })}
                      className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent"
                    />
                    <input
                      type="text"
                      value={customKit.text}
                      onChange={(e) => setCustomKit({ ...customKit, text: e.target.value })}
                      className="w-full bg-transparent font-mono text-xs uppercase text-on-surface focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Data Colors Swatches Row */}
              <div className="flex flex-col gap-2 pt-2">
                <label className="text-[11px] font-semibold text-on-surface-variant">
                  Power BI 8-Color Data Palette
                </label>
                <div className="grid grid-cols-4 gap-2 sm:grid-cols-8">
                  {customKit.dataColors.map((dc, idx) => (
                    <div
                      key={idx}
                      className="flex flex-col items-center gap-1 rounded-lg border border-outline-variant/40 bg-surface-container-low p-1.5"
                    >
                      <input
                        type="color"
                        value={dc}
                        onChange={(e) => {
                          const updated = [...customKit.dataColors];
                          updated[idx] = e.target.value;
                          setCustomKit({ ...customKit, dataColors: updated });
                        }}
                        className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent"
                      />
                      <span className="font-mono text-[9px] uppercase text-on-surface-variant">
                        {dc}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* LIVE DASHBOARD PREVIEW CANVAS */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="font-title-sm text-xs font-bold uppercase tracking-wider text-on-surface">
                Live Studio Canvas Simulation
              </span>
              <span className="text-[11px] font-medium text-on-surface-variant">
                1280 × 720 Native Power BI Ratio
              </span>
            </div>

            {/* The Canvas Frame */}
            <div
              className="relative overflow-hidden rounded-3xl border border-black/10 p-6 shadow-xl transition-colors duration-300"
              style={{
                backgroundColor: customKit.canvas,
                color: customKit.text,
              }}
            >
              {/* Simulated Power BI Top Bar */}
              <div className="flex items-center justify-between border-b pb-4" style={{ borderColor: `${customKit.text}15` }}>
                <div className="flex items-center gap-3">
                  <span
                    className="flex h-7 w-7 items-center justify-center rounded-full font-bold shadow-sm"
                    style={{ backgroundColor: customKit.accent, color: "#1B1C1C" }}
                  >
                    <Icon name="dashboard" size={16} />
                  </span>
                  <div>
                    <div className="font-bold tracking-tight text-sm sm:text-base" style={{ fontFamily: customKit.fonts.display }}>
                      Enterprise Performance Cockpit
                    </div>
                    <div className="text-[11px]" style={{ color: customKit.muted }}>
                      Daily Executive Synthesis • Real-Time DirectQuery
                    </div>
                  </div>
                </div>

                {/* Simulated Filter Pills */}
                <div className="hidden sm:flex items-center gap-2">
                  <span
                    className="rounded-full px-2.5 py-0.5 text-[10px] font-bold"
                    style={{ backgroundColor: customKit.accent, color: "#1B1C1C" }}
                  >
                    CY 2026 Q3
                  </span>
                  <span
                    className="rounded-full border px-2.5 py-0.5 text-[10px] font-medium"
                    style={{
                      borderColor: `${customKit.text}25`,
                      color: customKit.text,
                      backgroundColor: `${customKit.card}80`,
                    }}
                  >
                    All Regions
                  </span>
                </div>
              </div>

              {/* Simulated KPI Grid */}
              <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                {/* KPI Card 1 */}
                <div
                  className="flex flex-col justify-between p-4 shadow-sm transition-all"
                  style={{
                    backgroundColor: customKit.card,
                    borderRadius: `${customKit.borderRadius}px`,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold" style={{ color: customKit.muted }}>
                      Gross Merchandise Val
                    </span>
                    <span
                      className="flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold"
                      style={{ backgroundColor: `${customKit.accent}25`, color: customKit.text }}
                    >
                      $
                    </span>
                  </div>
                  <div className="mt-2 font-mono text-2xl font-bold tracking-tight">
                    $4,892,400
                  </div>
                  <div className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold text-emerald-600">
                    <Icon name="trending_up" size={14} />
                    <span>+14.8% vs last month</span>
                  </div>
                </div>

                {/* KPI Card 2 */}
                <div
                  className="flex flex-col justify-between p-4 shadow-sm transition-all"
                  style={{
                    backgroundColor: customKit.card,
                    borderRadius: `${customKit.borderRadius}px`,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold" style={{ color: customKit.muted }}>
                      Active Logistics Fleets
                    </span>
                    <span
                      className="flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold"
                      style={{ backgroundColor: `${customKit.secondaryAccent}25`, color: customKit.text }}
                    >
                      #
                    </span>
                  </div>
                  <div className="mt-2 font-mono text-2xl font-bold tracking-tight">
                    1,280 Units
                  </div>
                  <div className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold text-emerald-600">
                    <Icon name="check_circle" size={14} />
                    <span>99.8% On-Time SLA</span>
                  </div>
                </div>

                {/* KPI Card 3 */}
                <div
                  className="flex flex-col justify-between p-4 shadow-sm transition-all"
                  style={{
                    backgroundColor: customKit.card,
                    borderRadius: `${customKit.borderRadius}px`,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold" style={{ color: customKit.muted }}>
                      Net Operating Margin
                    </span>
                    <span
                      className="flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold"
                      style={{ backgroundColor: `${customKit.dataColors[2]}25`, color: customKit.text }}
                    >
                      %
                    </span>
                  </div>
                  <div className="mt-2 font-mono text-2xl font-bold tracking-tight">
                    28.4%
                  </div>
                  <div className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: customKit.muted }}>
                    <span>Target: 26.0% (Exceeded)</span>
                  </div>
                </div>
              </div>

              {/* Simulated Charts Row */}
              <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                {/* Chart 1: Categorical Bar Chart using Data Colors */}
                <div
                  className="p-4 shadow-sm"
                  style={{
                    backgroundColor: customKit.card,
                    borderRadius: `${customKit.borderRadius}px`,
                  }}
                >
                  <div className="flex items-center justify-between border-b pb-2" style={{ borderColor: `${customKit.text}10` }}>
                    <span className="text-xs font-bold" style={{ fontFamily: customKit.fonts.display }}>
                      Revenue Breakdown by Category
                    </span>
                    <span className="text-[10px]" style={{ color: customKit.muted }}>
                      8 Data Colors
                    </span>
                  </div>

                  {/* SVG Bar Chart */}
                  <div className="mt-3 h-28 w-full flex items-end justify-between gap-2 px-1">
                    {[
                      { val: 80, label: "Tech" },
                      { val: 65, label: "Retail" },
                      { val: 95, label: "Cloud" },
                      { val: 50, label: "Direct" },
                      { val: 70, label: "Auto" },
                      { val: 40, label: "Food" },
                    ].map((item, idx) => (
                      <div key={idx} className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end">
                        <div
                          className="w-full rounded-t transition-all duration-300"
                          style={{
                            height: `${item.val}%`,
                            backgroundColor: customKit.dataColors[idx % customKit.dataColors.length],
                          }}
                        />
                        <span className="text-[9px] font-mono" style={{ color: customKit.muted }}>
                          {item.label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Chart 2: Trend Area Curve with Accent Gradient */}
                <div
                  className="p-4 shadow-sm"
                  style={{
                    backgroundColor: customKit.card,
                    borderRadius: `${customKit.borderRadius}px`,
                  }}
                >
                  <div className="flex items-center justify-between border-b pb-2" style={{ borderColor: `${customKit.text}10` }}>
                    <span className="text-xs font-bold" style={{ fontFamily: customKit.fonts.display }}>
                      Monthly Velocity Trajectory
                    </span>
                    <span
                      className="rounded-full px-2 py-0.5 text-[9px] font-bold"
                      style={{ backgroundColor: `${customKit.accent}20`, color: customKit.text }}
                    >
                      30-Day Run
                    </span>
                  </div>

                  {/* SVG Area Sparkline */}
                  <div className="mt-3 h-28 w-full">
                    <svg viewBox="0 0 300 100" className="h-full w-full overflow-visible">
                      <defs>
                        <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={customKit.accent} stopOpacity="0.4" />
                          <stop offset="100%" stopColor={customKit.accent} stopOpacity="0.0" />
                        </linearGradient>
                      </defs>
                      <path
                        d="M 0 80 Q 50 40 100 60 T 200 30 T 300 10 L 300 100 L 0 100 Z"
                        fill="url(#areaGradient)"
                      />
                      <path
                        d="M 0 80 Q 50 40 100 60 T 200 30 T 300 10"
                        fill="none"
                        stroke={customKit.accent}
                        strokeWidth="3"
                        strokeLinecap="round"
                      />
                      <circle cx="200" cy="30" r="4" fill={customKit.accent} stroke="#FFFFFF" strokeWidth="2" />
                      <circle cx="300" cy="10" r="4" fill={customKit.accent} stroke="#FFFFFF" strokeWidth="2" />
                    </svg>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Contrast & Accessibility Metrics */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-on-surface-variant">Ink on Canvas</span>
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                  {Number(textVsCanvasRatio) >= 7 ? "AAA" : "AA"}
                </span>
              </div>
              <div className="mt-1 font-mono text-xl font-bold text-on-surface">
                {textVsCanvasRatio}:1
              </div>
              <p className="mt-1 text-[11px] text-on-surface-variant">
                Minimum recommended: 4.5:1
              </p>
            </div>

            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-on-surface-variant">Ink on Card Surface</span>
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                  {Number(textVsCardRatio) >= 7 ? "AAA" : "AA"}
                </span>
              </div>
              <div className="mt-1 font-mono text-xl font-bold text-on-surface">
                {textVsCardRatio}:1
              </div>
              <p className="mt-1 text-[11px] text-on-surface-variant">
                Minimum recommended: 4.5:1
              </p>
            </div>

            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-on-surface-variant">Accent Visibility</span>
                <span className="rounded-full bg-surface-container-high px-2 py-0.5 text-[10px] font-bold text-on-surface-variant">
                  {accentVsCardRatio}:1
                </span>
              </div>
              <div className="mt-1 font-mono text-xl font-bold text-on-surface">
                High Contrast
              </div>
              <p className="mt-1 text-[11px] text-on-surface-variant">
                Optimal for interactive buttons & pills
              </p>
            </div>
          </div>

          {/* Power BI Theme JSON Code Block */}
          <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-5 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Icon name="code" size={16} />
                <span className="font-title-sm text-xs font-bold uppercase tracking-wider text-on-surface">
                  Generated Power BI Theme JSON
                </span>
              </div>
              <button
                onClick={handleCopyJson}
                className="flex items-center gap-1 rounded-full border border-outline-variant/60 bg-surface-container-low px-3 py-1 text-xs font-semibold text-on-surface transition-all hover:bg-surface-container"
              >
                <Icon name={copiedJson ? "check" : "content_copy"} size={13} />
                {copiedJson ? "Copied!" : "Copy JSON"}
              </button>
            </div>

            <pre className="max-h-60 overflow-y-auto rounded-xl bg-charcoal p-4 font-mono text-xs text-glow">
              <code>{themeJson}</code>
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
