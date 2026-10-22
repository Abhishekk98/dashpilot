"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { listProjects, ProjectSummary } from "@/lib/api";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";

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

export default function ReportsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageFilter, setPageFilter] = useState<"all" | "multi" | "single">("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    listProjects()
      .then((data) => setProjects(data))
      .catch((err) => console.error("Failed to load projects", err))
      .finally(() => setLoading(false));
  }, []);

  // Built reports (has_build or stage >= 8)
  const builtReports = useMemo(() => {
    return projects.filter((p) => p.has_build || p.stage >= 8);
  }, [projects]);

  const filtered = useMemo(() => {
    return builtReports.filter((p) => {
      if (pageFilter === "multi" && p.pages_count <= 1) return false;
      if (pageFilter === "single" && p.pages_count > 1) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        return p.name.toLowerCase().includes(q) || (p.industry && p.industry.toLowerCase().includes(q));
      }
      return true;
    });
  }, [builtReports, pageFilter, search]);

  const stats = useMemo(() => {
    const readyCount = builtReports.filter((r) => r.has_build).length;
    const multiCount = builtReports.filter((r) => r.pages_count > 1).length;
    const totalMeasures = builtReports.reduce((sum, r) => sum + (r.measures_count || 0), 0);
    return { readyCount, multiCount, totalMeasures };
  }, [builtReports]);

  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* Header */}
      <section className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-6 border-b border-outline-variant/30">
        <div>
          <span className="font-label-sm text-label-sm text-secondary uppercase tracking-widest font-semibold flex items-center gap-1.5 mb-2">
            <Icon name="bar_chart" size={14} />
            Deliverables & Export
          </span>
          <h1 className="font-display-lg text-display-lg text-primary tracking-tight font-medium">
            Power BI Reports (.pbip)
          </h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-1.5 font-light">
            Production-grade Power BI Desktop projects authored with TMDL semantic models, DAX measures, and high-fidelity layouts.
          </p>
        </div>

        <PillButton href="/projects" arrow>
          View All Workflows
        </PillButton>
      </section>

      {/* Stats row */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl p-5 shadow-card border border-outline-variant/20 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center text-[#2E7D32] shrink-0">
            <Icon name="verified" size={24} />
          </div>
          <div>
            <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
              READY DELIVERABLES
            </span>
            <span className="font-display-lg text-headline-lg font-semibold text-primary">
              {stats.readyCount}
            </span>
          </div>
        </div>

        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl p-5 shadow-card border border-outline-variant/20 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center text-primary shrink-0">
            <Icon name="auto_stories" size={24} />
          </div>
          <div>
            <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
              MULTI-PAGE REPORTS
            </span>
            <span className="font-display-lg text-headline-lg font-semibold text-primary">
              {stats.multiCount}
            </span>
          </div>
        </div>

        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl p-5 shadow-card border border-outline-variant/20 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center text-secondary shrink-0">
            <Icon name="function" size={24} />
          </div>
          <div>
            <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
              DAX MEASURES
            </span>
            <span className="font-display-lg text-headline-lg font-semibold text-primary">
              {stats.totalMeasures.toLocaleString()}
            </span>
          </div>
        </div>

        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl p-5 shadow-card border border-outline-variant/20 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center text-primary shrink-0">
            <Icon name="code" size={24} />
          </div>
          <div>
            <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
              SCHEMA FORMAT
            </span>
            <span className="font-display-lg text-headline-lg font-semibold text-primary">
              PBIR 2.13.0
            </span>
          </div>
        </div>
      </section>

      {/* Filter and Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="relative w-full sm:w-80">
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-on-surface-variant">
            <Icon name="search" size={18} />
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search report titles..."
            className="w-full pl-10 pr-4 py-2.5 rounded-full bg-surface-container-lowest border border-outline-variant/40 text-[13px] text-primary focus:outline-none focus:border-primary transition-all placeholder:text-on-surface-variant/60 shadow-2xs"
          />
        </div>

        <div className="flex items-center p-1 rounded-full bg-surface-container-low border border-outline-variant/20 self-start sm:self-auto">
          <button
            onClick={() => setPageFilter("all")}
            className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
              pageFilter === "all"
                ? "bg-surface-container-lowest text-primary shadow-xs"
                : "text-on-surface-variant hover:text-primary"
            }`}
          >
            All Reports ({builtReports.length})
          </button>
          <button
            onClick={() => setPageFilter("multi")}
            className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
              pageFilter === "multi"
                ? "bg-surface-container-lowest text-primary shadow-xs"
                : "text-on-surface-variant hover:text-primary"
            }`}
          >
            Multi-Page ({stats.multiCount})
          </button>
          <button
            onClick={() => setPageFilter("single")}
            className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
              pageFilter === "single"
                ? "bg-surface-container-lowest text-primary shadow-xs"
                : "text-on-surface-variant hover:text-primary"
            }`}
          >
            Single-Page
          </button>
        </div>
      </div>

      {/* Report Cards Grid */}
      {loading ? (
        <div className="py-24 text-center text-on-surface-variant font-label-md">
          <Icon name="sync" size={24} className="animate-spin mb-2" />
          <p>Scanning deliverables...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-20 text-center bg-surface-container-lowest/80 rounded-[28px] border border-outline-variant/20 p-8 shadow-card">
          <div className="w-12 h-12 rounded-full bg-surface-container-low flex items-center justify-center mx-auto mb-3 text-on-surface-variant">
            <Icon name="bar_chart" size={24} />
          </div>
          <h3 className="font-headline-md text-headline-md font-semibold text-primary mb-1">
            No built reports found
          </h3>
          <p className="text-on-surface-variant text-[13px] max-w-md mx-auto mb-6">
            Advance a project through Step 9 (Build) to generate a full Power BI project deliverable.
          </p>
          <PillButton href="/projects" arrow>
            Browse Projects
          </PillButton>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((report) => {
            const accent = report.palette_accent || "#F8CF4B";

            return (
              <div
                key={report.id}
                className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card hover:shadow-card-hover transition-all duration-300 border border-outline-variant/20 flex flex-col justify-between group"
              >
                <div>
                  {/* Visual Header / Color Swatch */}
                  <div
                    className="h-28 rounded-2xl mb-4 p-4 flex flex-col justify-between relative overflow-hidden"
                    style={{
                      background: `linear-gradient(135deg, ${accent}22 0%, #1B1C2008 100%)`,
                      border: "1px solid rgba(0,0,0,0.06)",
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="px-2.5 py-0.5 rounded-full bg-surface-container-lowest/90 backdrop-blur-sm text-[11px] font-semibold text-primary shadow-2xs">
                        PBIP Package
                      </span>
                      <div className="flex items-center gap-1.5">
                        <span
                          className="w-3.5 h-3.5 rounded-full border border-black/10 shadow-2xs"
                          style={{ backgroundColor: accent }}
                          title={`Theme Accent: ${accent}`}
                        />
                        <span className="text-[10px] font-mono text-on-surface-variant font-medium">
                          {accent}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-baseline gap-2">
                      <span className="text-[20px] font-bold text-primary tracking-tight">
                        {report.pages_count} {report.pages_count === 1 ? "Page" : "Pages"}
                      </span>
                      <span className="text-[11px] text-on-surface-variant font-medium">
                        · {report.measures_count || 12} DAX Measures
                      </span>
                    </div>
                  </div>

                  {/* Title & Info */}
                  <h3 className="font-headline-md text-headline-md font-semibold text-primary mb-1 line-clamp-1 group-hover:text-secondary transition-colors">
                    <Link href={`/project/build?project=${report.id}`}>{report.name}</Link>
                  </h3>
                  <p className="text-[12px] text-on-surface-variant mb-4">
                    {report.files_count} dataset file(s) · {report.rows_total ? report.rows_total.toLocaleString() : "Processed"} rows · {formatBytes(report.size_bytes)}
                  </p>

                  {/* Feature Badges */}
                  <div className="flex flex-wrap gap-1.5 mb-5 text-[11px]">
                    <span className="px-2.5 py-0.5 rounded-full bg-surface-container-low text-primary font-medium">
                      Native Actions
                    </span>
                    <span className="px-2.5 py-0.5 rounded-full bg-surface-container-low text-primary font-medium">
                      TMDL Semantic Model
                    </span>
                    {report.pages_count > 1 && (
                      <span className="px-2.5 py-0.5 rounded-full bg-secondary-container text-on-secondary-fixed font-semibold">
                        Header Navigation
                      </span>
                    )}
                  </div>
                </div>

                {/* Footer Actions */}
                <div className="flex items-center justify-between gap-2 pt-3 border-t border-outline-variant/15">
                  <span className="text-[11px] text-on-surface-variant">
                    Built {timeAgo(report.updated_at)}
                  </span>

                  <div className="flex items-center gap-2">
                    <a
                      href={`http://127.0.0.1:8000/api/projects/${report.id}/build/download`}
                      download
                      className="px-3.5 py-1.5 rounded-full bg-surface-container-low hover:bg-surface-container-high text-primary text-[12px] font-medium transition-colors flex items-center gap-1.5"
                      title="Download ZIP with .pbip and Open Dashboard.cmd"
                    >
                      <Icon name="download" size={15} />
                      <span>ZIP</span>
                    </a>

                    <Link
                      href={`/project/build?project=${report.id}`}
                      className="px-4 py-1.5 rounded-full bg-primary text-on-primary hover:opacity-95 text-[12px] font-medium transition-all flex items-center gap-1"
                    >
                      <span>Build Hub</span>
                      <Icon name="arrow_forward" size={14} />
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
