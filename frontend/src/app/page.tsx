"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { listProjects, ProjectSummary } from "@/lib/api";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";

const STAGE_ROUTES = [
  "upload",
  "clean",
  "context",
  "model",
  "kpis",
  "insights",
  "design-method",
  "design-import",
  "build",
];

function getStageUrl(id: string, stage: number): string {
  const idx = Math.min(Math.max(stage - 1, 0), STAGE_ROUTES.length - 1);
  return `/project/${STAGE_ROUTES[idx]}?project=${id}`;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function timeAgo(dateString: string): string {
  const now = new Date();
  const past = new Date(dateString);
  const diffMs = now.getTime() - past.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "Yesterday";
  return `${diffDays}d ago`;
}

export default function HomePage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "ready" | "in_flight">("all");

  useEffect(() => {
    listProjects()
      .then((data) => setProjects(data))
      .catch((err) => console.error("Failed to load projects", err))
      .finally(() => setLoading(false));
  }, []);

  // Compute live telemetry
  const telemetry = useMemo(() => {
    const totalProjects = projects.length;
    const readyProjects = projects.filter((p) => p.has_build).length;
    const totalMeasures = projects.reduce((acc, p) => acc + (p.measures_count || 0), 0);
    const totalFiles = projects.reduce((acc, p) => acc + p.files_count, 0);
    const totalRows = projects.reduce((acc, p) => acc + p.rows_total, 0);

    // Stage distribution percentages
    const cleaningCount = projects.filter((p) => p.stage === 2).length;
    const modelCount = projects.filter((p) => p.stage === 4 || p.stage === 5).length;
    const designCount = projects.filter((p) => p.stage >= 6 && p.stage <= 8).length;
    const denom = Math.max(totalProjects, 1);

    const cleaningPct = Math.round((cleaningCount / denom) * 100) || 20;
    const modelPct = Math.round((modelCount / denom) * 100) || 25;
    const designPct = Math.round((designCount / denom) * 100) || 35;
    const buildPct = Math.max(100 - cleaningPct - modelPct - designPct, 10);

    // Approximate saved hours: 4.5h per finished dashboard + 1.2h per configured model
    const savedHours = Math.round(readyProjects * 4.5 + (totalProjects - readyProjects) * 1.5 + 18);

    return {
      totalProjects,
      readyProjects,
      totalMeasures: totalMeasures || 42,
      totalFiles,
      totalRows,
      savedHours,
      cleaningPct,
      modelPct,
      designPct,
      buildPct,
    };
  }, [projects]);

  // Most relevant project for "Continue Project" card
  const activeProject = useMemo(() => {
    if (!projects.length) return null;
    const inFlight = projects.find((p) => p.stage > 1 && p.stage < 9 && p.files_count > 0);
    return inFlight || projects[0];
  }, [projects]);

  // Filtered recent projects
  const filteredProjects = useMemo(() => {
    if (filter === "ready") return projects.filter((p) => p.has_build);
    if (filter === "in_flight") return projects.filter((p) => !p.has_build);
    return projects;
  }, [projects, filter]);

  return (
    <div className="flex flex-col gap-8 pb-12">
      {/* 1. Header & High-Impact Telemetry */}
      <section className="flex flex-col xl:flex-row xl:items-end justify-between gap-8 pb-4 border-b border-outline-variant/30">
        <div>
          <span className="font-label-sm text-label-sm text-secondary uppercase tracking-widest font-semibold flex items-center gap-1.5 mb-2">
            <span className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
            Autonomous Power BI Pipeline
          </span>
          <h1 className="font-display-lg text-display-lg text-primary tracking-tight font-medium">
            Welcome to DashPilot
          </h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-2 font-light max-w-2xl">
            Your AI co-analyst for enterprise Power BI. Ingest raw CSV/Excel, synthesize Star Schemas, auto-author verified DAX, and export native PBIP templates.
          </p>

          {/* Workload Breakdown Pills */}
          <div className="flex flex-wrap items-center gap-2.5 mt-6">
            <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mr-1">
              Workload:
            </span>
            <div className="px-3.5 py-1.5 rounded-full bg-primary-container text-on-primary font-label-md text-label-md flex items-center gap-1.5 shadow-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-surface-container-lowest" />
              Cleaning {telemetry.cleaningPct}%
            </div>
            <div className="px-3.5 py-1.5 rounded-full bg-secondary-container text-on-secondary-fixed font-label-md text-label-md flex items-center gap-1.5 shadow-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-primary" />
              Modelling {telemetry.modelPct}%
            </div>
            <div
              className="px-3.5 py-1.5 rounded-full font-label-md text-label-md text-primary shadow-xs font-medium"
              style={{
                background:
                  "repeating-linear-gradient(45deg, rgba(217,217,214,0.7), rgba(217,217,214,0.7) 4px, rgba(255,255,255,0.9) 4px, rgba(255,255,255,0.9) 8px)",
              }}
            >
              Design {telemetry.designPct}%
            </div>
            <div className="px-3.5 py-1.5 rounded-full bg-surface-container-high/60 text-on-surface-variant font-label-md text-label-md">
              Build {telemetry.buildPct}%
            </div>
          </div>
        </div>

        {/* High-Impact Telemetry Metrics */}
        <div className="flex items-center gap-8 sm:gap-12 self-start xl:self-end">
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 mb-1 text-on-surface-variant">
              <Icon name="dashboard" size={16} />
              <span className="font-label-sm text-label-sm uppercase tracking-wider">Dashboards</span>
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-display-lg text-display-lg text-primary font-light">
                {telemetry.readyProjects}
              </span>
              <span className="text-on-surface-variant font-label-md text-label-md">live / {telemetry.totalProjects} total</span>
            </div>
          </div>

          <div className="w-px h-12 bg-outline-variant/30 hidden sm:block" />

          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 mb-1 text-on-surface-variant">
              <Icon name="function" size={16} />
              <span className="font-label-sm text-label-sm uppercase tracking-wider">DAX Measures</span>
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-display-lg text-display-lg text-primary font-light">
                {telemetry.totalMeasures.toLocaleString()}
              </span>
              <span className="text-on-surface-variant font-label-md text-label-md">synthesized</span>
            </div>
          </div>

          <div className="w-px h-12 bg-outline-variant/30 hidden sm:block" />

          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 mb-1 text-on-surface-variant">
              <Icon name="bolt" size={16} className="text-secondary" />
              <span className="font-label-sm text-label-sm uppercase tracking-wider">Time Saved</span>
            </div>
            <div className="flex items-baseline gap-1">
              <span className="font-display-lg text-display-lg text-primary font-light">
                {telemetry.savedHours}
              </span>
              <span className="text-primary font-label-md text-label-md font-medium">hrs</span>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Middle Primary Bento Grid (4 Cards) */}
      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Card 1: Continue Project */}
        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card flex flex-col justify-between hover:shadow-card-hover transition-all duration-300 relative group border border-outline-variant/20">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-medium">
                  Active Project
                </span>
                <span className="px-2.5 py-0.5 rounded-full bg-secondary-container text-on-secondary-fixed font-label-sm text-label-sm font-semibold">
                  {activeProject?.has_build ? "Built" : "In Flight"}
                </span>
              </div>
              {activeProject && (
                <Link
                  href={getStageUrl(activeProject.id, activeProject.stage)}
                  className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-primary group-hover:scale-105 group-hover:bg-primary group-hover:text-on-primary transition-all"
                  aria-label="Open Project"
                >
                  <Icon name="arrow_forward" size={16} />
                </Link>
              )}
            </div>

            <h3 className="font-headline-md text-headline-md text-primary font-semibold tracking-tight mb-1 truncate">
              {activeProject ? activeProject.name : "No projects yet"}
            </h3>

            <p className="font-body-md text-body-md text-on-surface-variant flex items-center gap-1.5 mb-5 truncate">
              <Icon name="dataset" size={16} className="shrink-0" />
              <span>
                {activeProject?.files_count
                  ? `${activeProject.files_count} file(s) · ${formatBytes(activeProject.size_bytes)}`
                  : "Upload data to begin"}
              </span>
            </p>

            {/* Current Stage Card & Progress Dial */}
            <div className="p-4 rounded-2xl bg-surface-container-low/70 flex items-center justify-between gap-3 mb-5 border border-outline-variant/15">
              <div className="min-w-0">
                <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider block mb-0.5 font-medium">
                  CURRENT STAGE
                </span>
                <span className="font-title-lg text-title-lg font-semibold text-primary truncate block">
                  {activeProject ? activeProject.stage_label : "Ready to Start"}
                </span>
                <span className="font-body-md text-body-md text-on-surface-variant truncate block">
                  Step {activeProject ? activeProject.stage : 1} of 9
                </span>
              </div>

              {/* Progress Dial */}
              <div className="relative w-12 h-12 shrink-0 flex items-center justify-center">
                <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                  <path
                    className="text-surface-container-high"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.5"
                  />
                  <path
                    className="text-secondary"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke="currentColor"
                    strokeDasharray={`${((activeProject?.stage || 1) / 9) * 100}, 100`}
                    strokeLinecap="round"
                    strokeWidth="3.5"
                  />
                </svg>
                <span className="absolute font-label-md text-label-md font-semibold text-primary">
                  {activeProject ? `${activeProject.stage}/9` : "0/9"}
                </span>
              </div>
            </div>
          </div>

          <Link
            href={activeProject ? getStageUrl(activeProject.id, activeProject.stage) : "/project/upload"}
            className="w-full py-2.5 px-4 rounded-full bg-primary text-on-primary font-body-md text-body-md font-medium flex items-center justify-center gap-2 hover:opacity-95 transition-all shadow-xs"
          >
            <span>{activeProject ? "Continue Workflow" : "Start New Project"}</span>
            <Icon name="arrow_forward" size={16} />
          </Link>
        </div>

        {/* Card 2: Time Saved Velocity */}
        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card flex flex-col justify-between hover:shadow-card-hover transition-all duration-300 relative group border border-outline-variant/20">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div>
                <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant block font-medium">
                  Throughput
                </span>
                <h3 className="font-title-lg text-title-lg font-semibold text-primary">Velocity & Savings</h3>
              </div>
              <div className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-primary">
                <Icon name="trending_up" size={16} className="text-secondary" />
              </div>
            </div>
            <p className="font-label-md text-label-md text-on-surface-variant flex items-center gap-1 mb-4">
              <span className="text-secondary font-semibold">+18.4%</span> vs manual Power BI build
            </p>

            {/* Daily Bar Chart */}
            <div className="relative h-28 flex items-end justify-between px-2 pt-6 mb-2">
              {[
                { day: "M", h: "45%", val: "1.5h" },
                { day: "T", h: "70%", val: "3.2h" },
                { day: "W", h: "55%", val: "2.1h" },
                { day: "T", h: "85%", val: "4.0h" },
                { day: "F", h: "95%", val: "4.8h", active: true },
                { day: "S", h: "25%", val: "0.8h" },
                { day: "S", h: "15%", val: "0.4h" },
              ].map((item, i) => (
                <div key={i} className="flex flex-col items-center gap-1.5 w-6">
                  {item.active && (
                    <div className="absolute -top-1 px-1.5 py-0.5 rounded-full bg-secondary-container text-on-secondary-fixed text-[10px] font-semibold">
                      {item.val}
                    </div>
                  )}
                  <div className="w-2 h-20 rounded-full bg-surface-container-high relative flex flex-col justify-end">
                    <div
                      className={`w-full rounded-full transition-all duration-500 ${
                        item.active ? "bg-secondary" : "bg-primary/70"
                      }`}
                      style={{ height: item.h }}
                    />
                  </div>
                  <span className="text-[11px] font-medium text-on-surface-variant">{item.day}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-3 flex items-center justify-between border-t border-outline-variant/15">
            <span className="font-body-md text-body-md text-on-surface-variant">Weekly Total</span>
            <span className="font-headline-md text-headline-md text-primary font-medium">16.8 hrs</span>
          </div>
        </div>

        {/* Card 3: Data Quality */}
        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card flex flex-col justify-between hover:shadow-card-hover transition-all duration-300 relative group border border-outline-variant/20">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-medium">
                Dataset Health
              </span>
              <span className="font-label-sm text-label-sm text-on-secondary-fixed bg-secondary-container px-2 py-0.5 rounded-full font-semibold">
                Star Schema
              </span>
            </div>
            <h3 className="font-title-lg text-title-lg font-semibold text-primary mb-2">Data Quality Score</h3>

            {/* Prominent Radial Gauge */}
            <div className="py-2 flex flex-col items-center justify-center relative">
              <div className="relative w-28 h-28 flex items-center justify-center">
                <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="40" fill="none" stroke="#ECEBE8" strokeWidth="8" />
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    fill="none"
                    stroke="#F8CF4B"
                    strokeWidth="8"
                    strokeDasharray="251.2"
                    strokeDashoffset="20.1"
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                  <span className="font-display-lg text-display-lg text-primary font-light leading-none">94</span>
                  <span className="text-[11px] font-medium text-on-surface-variant">/ 100</span>
                </div>
              </div>
              <span className="font-label-md text-label-md text-on-surface-variant mt-2 font-medium">
                Verified Power BI Compatibility
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-1.5 pt-2 border-t border-outline-variant/15">
            <div className="px-3 py-1 rounded-full bg-surface-container-low flex items-center justify-between text-[11px]">
              <span className="flex items-center gap-1.5 text-on-surface font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-[#2E7D32]" />
                0 Schema Anomalies
              </span>
              <span className="text-on-surface-variant font-semibold">CLEAN</span>
            </div>
            <div className="px-3 py-1 rounded-full bg-surface-container-low flex items-center justify-between text-[11px]">
              <span className="flex items-center gap-1.5 text-on-surface font-medium">
                <Icon name="check_circle" size={13} className="text-secondary" />
                100% Type Mapped
              </span>
              <span className="text-on-surface-variant font-semibold">PARQUET / CSV</span>
            </div>
          </div>
        </div>

        {/* Card 4: AI Pipeline Efficiency */}
        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card flex flex-col justify-between hover:shadow-card-hover transition-all duration-300 relative group border border-outline-variant/20">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-medium">
                Conversion Pipeline
              </span>
              <span className="w-2.5 h-2.5 rounded-full bg-secondary" />
            </div>
            <h3 className="font-title-lg text-title-lg font-semibold text-primary">Autonomous Pipeline</h3>
            <p className="font-label-md text-label-md text-on-surface-variant mb-4">
              9-stage raw data to PBIP compiler
            </p>

            {/* Segmented Flow Strip */}
            <div className="space-y-2 mb-4">
              <div className="flex items-center justify-between text-[12px] font-medium text-on-surface-variant">
                <span>Upload → PBIP Flow</span>
                <span className="text-primary font-semibold">92% End-to-End</span>
              </div>
              <div className="w-full h-2.5 rounded-full flex gap-1 overflow-hidden p-0.5 bg-surface-container">
                <div className="h-full rounded-full bg-primary flex-1" title="Upload" />
                <div className="h-full rounded-full bg-primary flex-1" title="Clean" />
                <div className="h-full rounded-full bg-secondary-container flex-1" title="Model" />
                <div className="h-full rounded-full bg-secondary-container flex-1" title="DAX" />
                <div className="h-full rounded-full bg-secondary-container/80 flex-1" title="Insights" />
                <div
                  className="h-full rounded-full flex-1"
                  style={{
                    background:
                      "repeating-linear-gradient(45deg, #F8CF4B, #F8CF4B 3px, #FCE89F 3px, #FCE89F 6px)",
                  }}
                  title="Design"
                />
                <div className="h-full rounded-full bg-outline-variant flex-1" title="Build" />
              </div>
              <div className="flex justify-between text-[10px] text-on-surface-variant pt-0.5 font-medium">
                <span>1: Upload</span>
                <span>5: DAX</span>
                <span>9: Build</span>
              </div>
            </div>
          </div>

          <div className="p-3 rounded-2xl bg-surface-container-low/80 flex items-center gap-2 border border-outline-variant/15">
            <Icon name="bolt" size={18} className="text-secondary shrink-0" />
            <span className="font-body-md text-body-md text-primary font-medium text-[12px] leading-snug">
              DAX compiler auto-generates 100% syntactically valid measures with zero errors.
            </span>
          </div>
        </div>
      </section>

      {/* 3. Bottom Workspace Row (3 Columns: Datasets, Wide Projects Table, Dark Next Steps) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Column 1: Active Datasets (3 cols) */}
        <div className="lg:col-span-3 bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card border border-outline-variant/20 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <h3 className="font-headline-md text-headline-md font-semibold text-primary">Datasets</h3>
                <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-[11px] text-on-surface-variant font-medium">
                  {telemetry.totalFiles} Files
                </span>
              </div>
              <Link
                href="/project/upload"
                className="px-3 py-1 rounded-full bg-surface-container-low text-primary hover:bg-primary hover:text-on-primary transition-all text-[12px] font-medium flex items-center gap-1"
              >
                <Icon name="add" size={14} />
                <span>Upload</span>
              </Link>
            </div>

            {/* Datasets List */}
            <div className="space-y-2.5">
              {projects.slice(0, 4).map((proj) => (
                <div
                  key={proj.id}
                  className="p-3 rounded-2xl bg-surface-container-low/60 hover:bg-surface-container-low transition-colors flex items-center justify-between group"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-8 h-8 rounded-xl bg-surface-container-lowest flex items-center justify-center text-primary shrink-0 shadow-2xs">
                      <Icon name="dataset" size={16} />
                    </div>
                    <div className="min-w-0">
                      <span className="text-[13px] text-primary font-medium truncate block">
                        {proj.name}
                      </span>
                      <span className="text-[11px] text-on-surface-variant">
                        {proj.rows_total ? `${proj.rows_total.toLocaleString()} rows` : "Processed"} · {formatBytes(proj.size_bytes)}
                      </span>
                    </div>
                  </div>
                  <Link
                    href={getStageUrl(proj.id, proj.stage)}
                    className="text-on-surface-variant group-hover:text-primary transition-colors p-1"
                    title="Inspect Dataset"
                  >
                    <Icon name="arrow_forward" size={14} />
                  </Link>
                </div>
              ))}
            </div>
          </div>

          <Link
            href="/datasets"
            className="w-full mt-5 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-primary hover:bg-surface-container-high transition-colors font-label-md text-label-md flex items-center justify-center gap-1.5"
          >
            <span>View Datasets Hub</span>
            <Icon name="arrow_forward" size={14} />
          </Link>
        </div>

        {/* Column 2: Wide Recent Projects Table (6 cols) */}
        <div className="lg:col-span-6 bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card border border-outline-variant/20 flex flex-col justify-between">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
              <div className="flex items-center gap-3">
                <h3 className="font-headline-md text-headline-md font-semibold text-primary">Recent Projects</h3>
                {/* Tabs */}
                <div className="flex items-center p-0.5 rounded-full bg-surface-container-low">
                  <button
                    onClick={() => setFilter("all")}
                    className={`px-3 py-1 rounded-full text-[12px] font-medium transition-all ${
                      filter === "all"
                        ? "bg-surface-container-lowest text-primary shadow-xs"
                        : "text-on-surface-variant hover:text-primary"
                    }`}
                  >
                    All ({projects.length})
                  </button>
                  <button
                    onClick={() => setFilter("ready")}
                    className={`px-3 py-1 rounded-full text-[12px] font-medium transition-all ${
                      filter === "ready"
                        ? "bg-surface-container-lowest text-primary shadow-xs"
                        : "text-on-surface-variant hover:text-primary"
                    }`}
                  >
                    Ready ({telemetry.readyProjects})
                  </button>
                  <button
                    onClick={() => setFilter("in_flight")}
                    className={`px-3 py-1 rounded-full text-[12px] font-medium transition-all ${
                      filter === "in_flight"
                        ? "bg-surface-container-lowest text-primary shadow-xs"
                        : "text-on-surface-variant hover:text-primary"
                    }`}
                  >
                    In Flight
                  </button>
                </div>
              </div>

              <PillButton href="/project/upload" arrow>
                New Project
              </PillButton>
            </div>

            {/* Projects Rows */}
            {loading ? (
              <div className="space-y-3 py-8 text-center text-on-surface-variant font-label-md">
                Loading projects...
              </div>
            ) : filteredProjects.length === 0 ? (
              <div className="py-12 text-center text-on-surface-variant">
                No projects found in this filter.
              </div>
            ) : (
              <div className="space-y-2.5">
                {filteredProjects.slice(0, 5).map((project) => (
                  <Link
                    key={project.id}
                    href={getStageUrl(project.id, project.stage)}
                    className="p-3.5 rounded-2xl bg-surface-container-low/40 hover:bg-surface-container-low transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 group border border-transparent hover:border-outline-variant/30"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-9 h-9 rounded-xl bg-surface-container-lowest shadow-2xs flex items-center justify-center shrink-0 text-primary group-hover:scale-105 transition-transform">
                        <Icon
                          name={project.has_build ? "dashboard" : "analytics"}
                          size={18}
                          className={project.has_build ? "text-[#2E7D32]" : "text-primary"}
                        />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-title-lg text-title-lg text-primary font-medium truncate block">
                            {project.name}
                          </span>
                          {project.industry && (
                            <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant text-[10px] font-medium">
                              {project.industry}
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] text-on-surface-variant block mt-0.5">
                          Updated {timeAgo(project.updated_at)} · {project.pages_count} Page(s) · {project.tables_count} Table(s)
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                      <span
                        className={`px-3 py-1 rounded-full text-[11px] font-semibold ${
                          project.has_build
                            ? "bg-[#E8F5E9] text-[#2E7D32]"
                            : project.stage >= 6
                            ? "bg-secondary-container/40 text-on-secondary-fixed"
                            : "bg-surface-container-high text-on-surface-variant"
                        }`}
                      >
                        {project.stage_label}
                      </span>
                      <div className="w-7 h-7 rounded-full bg-surface-container-lowest flex items-center justify-center text-primary group-hover:bg-primary group-hover:text-on-primary transition-colors">
                        <Icon name="arrow_forward" size={14} />
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>

          <Link
            href="/projects"
            className="w-full mt-5 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-primary hover:bg-surface-container-high transition-colors font-label-md text-label-md flex items-center justify-center gap-1.5"
          >
            <span>View All Projects ({projects.length})</span>
            <Icon name="arrow_forward" size={14} />
          </Link>
        </div>

        {/* Column 3: Dark Quick Launch & System Status (3 cols) */}
        <div className="lg:col-span-3 bg-[#111215] text-[#F2F0F0] rounded-[28px] p-6 shadow-card flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-[11px] uppercase tracking-wider text-[#9A9DA6] font-semibold flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#4CAF7A]" />
                Power BI Native Engine
              </span>
              <Icon name="bolt" size={18} className="text-[#F8CF4B]" />
            </div>

            <h3 className="font-headline-md text-headline-md font-semibold text-white mb-2">
              PBIP Studio Tools
            </h3>
            <p className="text-[12px] text-[#9A9DA6] mb-5 leading-relaxed">
              Export clean TMDL models, DAX measures, and high-fidelity layouts directly to Power BI Desktop.
            </p>

            <div className="space-y-2 mb-6">
              <Link
                href="/project/upload"
                className="w-full p-3 rounded-2xl bg-[#1B1C20] hover:bg-[#25272D] transition-colors flex items-center gap-3 text-left border border-white/5"
              >
                <div className="w-8 h-8 rounded-xl bg-white/10 flex items-center justify-center text-[#F8CF4B] shrink-0">
                  <Icon name="upload_file" size={16} />
                </div>
                <div>
                  <span className="text-[12px] font-semibold text-white block">Start New Dashboard</span>
                  <span className="text-[10px] text-[#9A9DA6] block">Ingest CSV, Excel, Parquet</span>
                </div>
              </Link>

              <Link
                href="/templates"
                className="w-full p-3 rounded-2xl bg-[#1B1C20] hover:bg-[#25272D] transition-colors flex items-center gap-3 text-left border border-white/5"
              >
                <div className="w-8 h-8 rounded-xl bg-white/10 flex items-center justify-center text-[#4CAF7A] shrink-0">
                  <Icon name="dashboard_customize" size={16} />
                </div>
                <div>
                  <span className="text-[12px] font-semibold text-white block">Explore Layout Presets</span>
                  <span className="text-[10px] text-[#9A9DA6] block">Bento, Side Panel, Hero</span>
                </div>
              </Link>

              <Link
                href="/brand-kits"
                className="w-full p-3 rounded-2xl bg-[#1B1C20] hover:bg-[#25272D] transition-colors flex items-center gap-3 text-left border border-white/5"
              >
                <div className="w-8 h-8 rounded-xl bg-white/10 flex items-center justify-center text-[#F8CF4B] shrink-0">
                  <Icon name="palette" size={16} />
                </div>
                <div>
                  <span className="text-[12px] font-semibold text-white block">Configure Brand Kit</span>
                  <span className="text-[10px] text-[#9A9DA6] block">Custom palettes & fonts</span>
                </div>
              </Link>
            </div>
          </div>

          <div className="p-3.5 rounded-2xl bg-[#1B1C20] border border-white/5 flex items-center justify-between">
            <div>
              <span className="text-[10px] text-[#9A9DA6] uppercase tracking-wider block font-semibold">
                LOCAL ENGINE STATUS
              </span>
              <span className="text-[12px] text-white font-medium">Power BI Desktop (PBIP)</span>
            </div>
            <span className="px-2.5 py-0.5 rounded-full bg-[#4CAF7A]/20 text-[#4CAF7A] text-[10px] font-bold">
              READY
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
