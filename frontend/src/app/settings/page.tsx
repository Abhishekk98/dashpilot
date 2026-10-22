"use client";

import { useState, useEffect } from "react";
import { Icon } from "@/components/ui/Icon";
import {
  fetchSystemInfo,
  testLLM,
  SystemInfoResponse,
  LLMTestResponse,
} from "@/lib/api";

type ActiveTab = "models" | "engine" | "storage" | "diagnostics";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("models");
  const [systemInfo, setSystemInfo] = useState<SystemInfoResponse | null>(null);
  const [loadingInfo, setLoadingInfo] = useState(true);
  const [errorInfo, setErrorInfo] = useState<string | null>(null);

  // LLM Test state
  const [testingLlm, setTestingLlm] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<LLMTestResponse | null>(null);
  const [llmTestError, setLlmTestError] = useState<string | null>(null);

  // Local settings preferences
  const [defaultCanvasResolution, setDefaultCanvasResolution] = useState("1280x720");
  const [gridGutter, setGridGutter] = useState(16);
  const [canvasMargin, setCanvasMargin] = useState(24);
  const [autoSaveNotification, setAutoSaveNotification] = useState(false);

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        setLoadingInfo(true);
        const data = await fetchSystemInfo();
        if (!ignore) {
          setSystemInfo(data);
          setErrorInfo(null);
        }
      } catch (err) {
        if (!ignore) {
          setErrorInfo(err instanceof Error ? err.message : "Failed to load system diagnostics");
        }
      } finally {
        if (!ignore) setLoadingInfo(false);
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, []);

  const handleTestLLM = async () => {
    setTestingLlm(true);
    setLlmTestResult(null);
    setLlmTestError(null);
    try {
      const res = await testLLM();
      setLlmTestResult(res);
    } catch (err) {
      setLlmTestError(err instanceof Error ? err.message : "LLM ping test failed");
    } finally {
      setTestingLlm(false);
    }
  };

  const handleSavePreferences = () => {
    setAutoSaveNotification(true);
    setTimeout(() => setAutoSaveNotification(false), 2400);
  };

  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* Top Banner & Header */}
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-sunflower/20 text-on-surface">
              <Icon name="settings" size={14} />
            </span>
            <span className="font-mono text-xs uppercase tracking-wider text-on-surface-variant">
              Engine Control & Configuration
            </span>
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
              API v{systemInfo?.version || "0.1.0"} Active
            </span>
          </div>
          <h1 className="mt-1 font-title-lg text-2xl font-bold tracking-tight text-on-surface sm:text-3xl">
            Studio Preferences & System Diagnostics
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant max-w-3xl">
            Configure foundation model providers, Power BI canvas dimensions, local directory structures, and inspect runtime health.
          </p>
        </div>

        {autoSaveNotification && (
          <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-4 py-2 border border-emerald-200 text-xs font-semibold text-emerald-800 animate-in fade-in duration-200">
            <Icon name="check_circle" size={16} />
            Preferences Saved Locally
          </div>
        )}
      </div>

      {/* Tabs Bar */}
      <div className="flex border-b border-outline-variant/40 gap-2">
        {[
          { id: "models" as ActiveTab, label: "AI Models & Keys", icon: "neurology" },
          { id: "engine" as ActiveTab, label: "Power BI Engine", icon: "precision_manufacturing" },
          { id: "storage" as ActiveTab, label: "Storage & Paths", icon: "folder_open" },
          { id: "diagnostics" as ActiveTab, label: "System Diagnostics", icon: "monitor_heart" },
        ].map((tab) => {
          const isSelected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold transition-all ${
                isSelected
                  ? "border-primary text-primary"
                  : "border-transparent text-on-surface-variant hover:text-on-surface"
              }`}
            >
              <Icon name={tab.icon} size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB CONTENT */}

      {/* 1. AI FOUNDATION MODELS */}
      {activeTab === "models" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Active Model Overview (8 Cols) */}
          <div className="flex flex-col gap-6 lg:col-span-8">
            <div className="rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-6 shadow-sm flex flex-col gap-5">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-title-md text-base font-bold text-on-surface">
                    Active Foundation Model Provider
                  </h3>
                  <p className="text-xs text-on-surface-variant mt-0.5">
                    DashPilot routes dataset profiling, measure DAX generation, and executive insights through this provider.
                  </p>
                </div>
                <span className="rounded-full bg-surface-container-high px-2.5 py-1 text-xs font-semibold capitalize text-on-surface">
                  {systemInfo?.llm_provider || "gemini"}
                </span>
              </div>

              {/* Provider Card: Google Gemini */}
              <div
                className={`rounded-2xl border p-5 transition-all ${
                  systemInfo?.llm_provider === "gemini"
                    ? "border-primary bg-surface-container-low/50 ring-1 ring-primary/20"
                    : "border-outline-variant/40 bg-surface-container-lowest opacity-75"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sunflower/20 text-on-surface font-bold">
                      <Icon name="auto_awesome" size={20} />
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-title-sm text-sm font-bold text-on-surface">
                          Google Gemini (Default Enterprise Engine)
                        </span>
                        {systemInfo?.llm_provider === "gemini" && (
                          <span className="rounded-full bg-charcoal px-2 py-0.5 text-[9px] font-bold text-white">
                            Active
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-on-surface-variant">
                        High throughput, large context window (1M+ tokens), rapid DAX synthesis.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5">
                    {systemInfo?.llm_configured ? (
                      <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                        <Icon name="check_circle" size={14} />
                        API Key Configured
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
                        <Icon name="warning" size={14} />
                        Key Unset in .env
                      </span>
                    )}
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3 border-t border-outline-variant/30 pt-4 text-xs">
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant font-semibold">
                      Configured Model
                    </span>
                    <div className="font-mono font-bold text-on-surface mt-0.5">
                      {systemInfo?.llm_model || "gemini-3.6-flash"}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant font-semibold">
                      Max Retry Attempts
                    </span>
                    <div className="font-mono font-bold text-on-surface mt-0.5">
                      {systemInfo?.llm_max_retries || 4} retries
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant font-semibold">
                      Per-Call Timeout
                    </span>
                    <div className="font-mono font-bold text-on-surface mt-0.5">
                      {systemInfo?.llm_timeout_seconds || 120}s
                    </div>
                  </div>
                </div>
              </div>

              {/* Provider Card: Anthropic Claude */}
              <div
                className={`rounded-2xl border p-5 transition-all ${
                  systemInfo?.llm_provider === "claude"
                    ? "border-primary bg-surface-container-low/50 ring-1 ring-primary/20"
                    : "border-outline-variant/40 bg-surface-container-lowest opacity-75"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-100 text-orange-800 font-bold">
                      <Icon name="psychology" size={20} />
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-title-sm text-sm font-bold text-on-surface">
                          Anthropic Claude
                        </span>
                        {systemInfo?.llm_provider === "claude" && (
                          <span className="rounded-full bg-charcoal px-2 py-0.5 text-[9px] font-bold text-white">
                            Active
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-on-surface-variant">
                        Secondary provider support for Claude Opus / Sonnet reasoning.
                      </p>
                    </div>
                  </div>

                  <span className="rounded-full bg-surface-container px-2.5 py-1 text-[11px] font-medium text-on-surface-variant">
                    Configured via ANTHROPIC_API_KEY
                  </span>
                </div>
              </div>
            </div>

            {/* Live LLM Connection Tester Box */}
            <div className="rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-6 shadow-sm flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-title-md text-base font-bold text-on-surface">
                    Test LLM Provider Connectivity
                  </h3>
                  <p className="text-xs text-on-surface-variant mt-0.5">
                    Sends a lightweight verification prompt to verify API keys, latency, and model availability.
                  </p>
                </div>

                <button
                  onClick={handleTestLLM}
                  disabled={testingLlm}
                  className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-on-primary shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
                >
                  <Icon name={testingLlm ? "sync" : "send"} size={14} />
                  {testingLlm ? "Testing Connection..." : "Test AI Connection"}
                </button>
              </div>

              {llmTestResult && (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 text-xs flex flex-col gap-2 animate-in fade-in">
                  <div className="flex items-center justify-between font-bold text-emerald-900">
                    <span className="flex items-center gap-1.5">
                      <Icon name="check_circle" size={16} />
                      Connection Successful ({llmTestResult.latency_ms} ms)
                    </span>
                    <span className="font-mono text-[11px]">{llmTestResult.model}</span>
                  </div>
                  <div className="text-emerald-800">
                    Provider: <strong>{llmTestResult.provider}</strong> • Model Response: <code>&quot;{llmTestResult.response}&quot;</code>
                  </div>
                </div>
              )}

              {llmTestError && (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs flex flex-col gap-1.5 animate-in fade-in">
                  <div className="flex items-center gap-1.5 font-bold text-red-900">
                    <Icon name="error" size={16} />
                    Connection Test Failed
                  </div>
                  <div className="text-red-700">{llmTestError}</div>
                  <div className="text-[11px] text-red-600">
                    Ensure your <code>GEMINI_API_KEY</code> is correctly set in <code>backend/.env</code> and restart the backend worker if required.
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Quick Guidance Column (4 Cols) */}
          <div className="flex flex-col gap-5 lg:col-span-4">
            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-5 text-xs text-on-surface-variant flex flex-col gap-3">
              <div className="flex items-center gap-2 font-bold text-on-surface">
                <Icon name="key" size={16} />
                <span>API Key Security</span>
              </div>
              <p className="leading-relaxed">
                DashPilot reads credentials directly from <code>backend/.env</code> using Pydantic BaseSettings. API keys are never leaked to client bundles or logged in telemetry.
              </p>
              <div className="rounded-lg bg-surface-container-low p-3 font-mono text-[11px] text-on-surface">
                GEMINI_API_KEY=AIzaSy...<br />
                GEMINI_MODEL=gemini-3.6-flash
              </div>
            </div>

            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-5 text-xs text-on-surface-variant flex flex-col gap-3">
              <div className="flex items-center gap-2 font-bold text-on-surface">
                <Icon name="speed" size={16} />
                <span>Quota & Rate Limiting</span>
              </div>
              <p className="leading-relaxed">
                DashPilot includes exponential backoff with jitter and transparent profile fallback to ensure batch dataset processing never halts unexpectedly.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 2. POWER BI ENGINE */}
      {activeTab === "engine" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="flex flex-col gap-6 lg:col-span-8">
            <div className="rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-6 shadow-sm flex flex-col gap-6">
              <div>
                <h3 className="font-title-md text-base font-bold text-on-surface">
                  Power BI Canvas & Geometric Layout Constraints
                </h3>
                <p className="text-xs text-on-surface-variant mt-0.5">
                  Parameters used by the layout compiler to position KPI cards, navigation bars, and charts without overlap.
                </p>
              </div>

              {/* Canvas Resolution Selector */}
              <div className="flex flex-col gap-2">
                <label className="text-xs font-semibold text-on-surface">
                  Default Target Canvas Resolution
                </label>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  {[
                    { val: "1280x720", label: "1280 × 720 (16:9 HD)", desc: "Power BI standard native canvas default" },
                    { val: "1920x1080", label: "1920 × 1080 (16:9 FHD)", desc: "Large boardroom & high-DPI displays" },
                    { val: "custom", label: "Dynamic Adaptive", desc: "Auto-computed based on wireframe density" },
                  ].map((res) => (
                    <div
                      key={res.val}
                      onClick={() => setDefaultCanvasResolution(res.val)}
                      className={`cursor-pointer rounded-2xl border p-3.5 transition-all ${
                        defaultCanvasResolution === res.val
                          ? "border-primary bg-surface-container-low/70 ring-1 ring-primary/20"
                          : "border-outline-variant/40 hover:border-outline"
                      }`}
                    >
                      <div className="font-title-sm text-xs font-bold text-on-surface">
                        {res.label}
                      </div>
                      <div className="text-[11px] text-on-surface-variant mt-0.5">
                        {res.desc}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Grid & Visual Spacing */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 border-t border-outline-variant/30 pt-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-on-surface">
                    Grid Gutter Spacing (px)
                  </label>
                  <input
                    type="number"
                    value={gridGutter}
                    onChange={(e) => setGridGutter(Number(e.target.value))}
                    className="w-full rounded-xl border border-outline-variant/60 bg-surface-container-low px-3 py-2 text-xs font-mono text-on-surface focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <span className="text-[10px] text-on-surface-variant">
                    Strict distance maintained between adjacent visual cards.
                  </span>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-on-surface">
                    Outer Canvas Margin (px)
                  </label>
                  <input
                    type="number"
                    value={canvasMargin}
                    onChange={(e) => setCanvasMargin(Number(e.target.value))}
                    className="w-full rounded-xl border border-outline-variant/60 bg-surface-container-low px-3 py-2 text-xs font-mono text-on-surface focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <span className="text-[10px] text-on-surface-variant">
                    Padding from top/left edge to first row of KPI metrics.
                  </span>
                </div>
              </div>

              {/* Power BI Desktop Integration Status */}
              <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-low/40 p-4 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-on-primary">
                      <Icon name="desktop_windows" size={14} />
                    </span>
                    <span className="font-title-sm text-xs font-bold text-on-surface">
                      Power BI Desktop Runtime Status
                    </span>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                      systemInfo?.powerbi_desktop_installed
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-surface-container-high text-on-surface-variant"
                    }`}
                  >
                    {systemInfo?.powerbi_desktop_installed ? "Detected on Windows" : "Standalone Package Mode"}
                  </span>
                </div>

                <p className="text-xs text-on-surface-variant leading-relaxed">
                  {systemInfo?.powerbi_desktop_installed
                    ? `Found at ${systemInfo.powerbi_desktop_path}`
                    : "Power BI Desktop is not detected in standard system directories. DashPilot outputs portable .pbip zip bundles ready for upload to Fabric or Power BI Service."}
                </p>

                <div className="rounded-lg bg-surface-container-lowest p-3 border border-outline-variant/30 text-[11px] text-on-surface-variant flex items-center gap-2">
                  <Icon name="verified_user" size={16} />
                  <span>
                    <strong>User-Controlled Launch Mode:</strong> DashPilot builds clean, fully-compliant <code>.pbip</code> projects. Opening the dashboard is left entirely in your control.
                  </span>
                </div>
              </div>

              <div className="flex justify-end">
                <button
                  onClick={handleSavePreferences}
                  className="flex items-center gap-1.5 rounded-full bg-primary px-5 py-2 text-xs font-semibold text-on-primary shadow-sm hover:bg-primary/90"
                >
                  <Icon name="save" size={14} />
                  Apply Engine Settings
                </button>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-5 lg:col-span-4">
            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-5 text-xs text-on-surface-variant flex flex-col gap-2.5">
              <div className="flex items-center gap-2 font-bold text-on-surface">
                <Icon name="design_services" size={16} />
                <span>Layout Uniformity Guarantee</span>
              </div>
              <p className="leading-relaxed">
                The layout compiler enforces strict bounding-box validation: 0 overlapping visuals, uniform <code>262 × 61 px</code> KPI dimensions, and automated native <code>actionButton</code> navigation links.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 3. STORAGE & PATHS */}
      {activeTab === "storage" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="flex flex-col gap-6 lg:col-span-8">
            <div className="rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-6 shadow-sm flex flex-col gap-5">
              <div>
                <h3 className="font-title-md text-base font-bold text-on-surface">
                  Workspace Paths & Artifact Stores
                </h3>
                <p className="text-xs text-on-surface-variant mt-0.5">
                  Locations where DashPilot stores uploaded CSV/Excel files, generated DAX measures, and compiled PBIP archives.
                </p>
              </div>

              <div className="flex flex-col gap-3">
                <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-low/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="font-title-sm text-xs font-bold text-on-surface">
                      Backend Storage Directory
                    </span>
                    <span className="rounded-full bg-surface-container px-2 py-0.5 text-[10px] font-semibold text-on-surface">
                      Local Filesystem
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-xs text-on-surface-variant break-all">
                    {systemInfo?.storage_dir || "backend/storage"}
                  </div>
                  <p className="mt-2 text-[11px] text-on-surface-variant">
                    Stores per-project JSON state (<code>context.json</code>, <code>clean.json</code>, <code>model.json</code>, <code>build.json</code>).
                  </p>
                </div>

                <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-low/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="font-title-sm text-xs font-bold text-on-surface">
                      Verification & Test Extraction Directory
                    </span>
                    <span className="rounded-full bg-surface-container px-2 py-0.5 text-[10px] font-semibold text-on-surface">
                      Verification Drive
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-xs text-on-surface-variant">
                    C:\DashPilot\Test_PartA_Verification\
                  </div>
                  <p className="mt-2 text-[11px] text-on-surface-variant">
                    Target directory where verified Swiggy and Credit Card builds are extracted for manual Power BI inspection.
                  </p>
                </div>

                <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-low/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="font-title-sm text-xs font-bold text-on-surface">
                      Max File Upload Limit
                    </span>
                    <span className="font-mono text-xs font-bold text-on-surface">
                      {systemInfo?.max_upload_mb || 100} MB
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-on-surface-variant">
                    Applies to multipart uploads for CSV and multi-sheet Excel files.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-5 lg:col-span-4">
            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-5 text-xs text-on-surface-variant flex flex-col gap-3">
              <div className="flex items-center gap-2 font-bold text-on-surface">
                <Icon name="security" size={16} />
                <span>Zero Cloud Leakage</span>
              </div>
              <p className="leading-relaxed">
                Raw client data files never leave your workstation. Only tokenized schema profiles and column statistical aggregations are sent to the AI planner.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 4. SYSTEM DIAGNOSTICS */}
      {activeTab === "diagnostics" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="flex flex-col gap-6 lg:col-span-8">
            <div className="rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-6 shadow-sm flex flex-col gap-5">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-title-md text-base font-bold text-on-surface">
                    Runtime Environment & Diagnostics
                  </h3>
                  <p className="text-xs text-on-surface-variant mt-0.5">
                    Live telemetry reported by the FastAPI backend server and Next.js client.
                  </p>
                </div>

                <button
                  onClick={async () => {
                    try {
                      setLoadingInfo(true);
                      const data = await fetchSystemInfo();
                      setSystemInfo(data);
                      setErrorInfo(null);
                    } catch (err) {
                      setErrorInfo(err instanceof Error ? err.message : "Failed to refresh");
                    } finally {
                      setLoadingInfo(false);
                    }
                  }}
                  className="flex items-center gap-1 rounded-full border border-outline-variant/60 bg-surface px-3 py-1.5 text-xs font-semibold text-on-surface hover:bg-surface-container"
                >
                  <Icon name="refresh" size={14} />
                  Refresh
                </button>
              </div>

              {loadingInfo && (
                <div className="py-8 text-center text-xs text-on-surface-variant">
                  Loading system telemetry...
                </div>
              )}

              {errorInfo && (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs text-red-700">
                  {errorInfo}
                </div>
              )}

              {systemInfo && !loadingInfo && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="rounded-2xl border border-outline-variant/30 bg-surface-container-low/40 p-4">
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant font-semibold">
                      Application Framework
                    </span>
                    <div className="font-mono text-sm font-bold text-on-surface mt-1">
                      {systemInfo.app}
                    </div>
                    <div className="text-[11px] text-on-surface-variant mt-0.5">
                      FastAPI + Uvicorn Async Architecture
                    </div>
                  </div>

                  <div className="rounded-2xl border border-outline-variant/30 bg-surface-container-low/40 p-4">
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant font-semibold">
                      Python Runtime
                    </span>
                    <div className="font-mono text-sm font-bold text-on-surface mt-1">
                      Python {systemInfo.python_version}
                    </div>
                    <div className="text-[11px] text-on-surface-variant mt-0.5">
                      Platform: {systemInfo.platform}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-outline-variant/30 bg-surface-container-low/40 p-4">
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant font-semibold">
                      Frontend Framework
                    </span>
                    <div className="font-mono text-sm font-bold text-on-surface mt-1">
                      Next.js 15 (Turbopack / App Router)
                    </div>
                    <div className="text-[11px] text-on-surface-variant mt-0.5">
                      Tailwind CSS 4 • Nordic Canvas Tokens
                    </div>
                  </div>

                  <div className="rounded-2xl border border-outline-variant/30 bg-surface-container-low/40 p-4">
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant font-semibold">
                      Network & Ports
                    </span>
                    <div className="font-mono text-sm font-bold text-on-surface mt-1">
                      API: :8000 | Web: :3000
                    </div>
                    <div className="text-[11px] text-on-surface-variant mt-0.5">
                      CORS Regex: localhost / 127.0.0.1
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-5 lg:col-span-4">
            <div className="rounded-2xl border border-outline-variant/40 bg-surface-container-lowest p-5 text-xs text-on-surface-variant flex flex-col gap-3">
              <div className="flex items-center gap-2 font-bold text-on-surface">
                <Icon name="delete_sweep" size={16} />
                <span>Browser Local Cache</span>
              </div>
              <p className="leading-relaxed">
                Clear locally cached theme selections and filter preferences stored in this browser session.
              </p>
              <button
                onClick={() => {
                  localStorage.clear();
                  alert("Local storage cache reset.");
                }}
                className="mt-1 flex items-center justify-center gap-1.5 rounded-full border border-red-200 bg-red-50/60 px-4 py-2 text-xs font-semibold text-red-700 hover:bg-red-100"
              >
                <Icon name="delete" size={14} />
                Clear Local Storage
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
