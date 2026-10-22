"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { listProjects, ProjectSummary, StoredFile } from "@/lib/api";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";

interface FlattenedDataset {
  file: StoredFile;
  projectId: string;
  projectName: string;
  projectStage: number;
  projectStageLabel: string;
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

export default function DatasetsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [formatFilter, setFormatFilter] = useState<"all" | "csv" | "excel">("all");

  useEffect(() => {
    listProjects()
      .then((data) => setProjects(data))
      .catch((err) => console.error("Failed to load projects", err))
      .finally(() => setLoading(false));
  }, []);

  // Flatten all files across projects
  const allDatasets = useMemo(() => {
    const list: FlattenedDataset[] = [];
    for (const p of projects) {
      for (const f of p.files || []) {
        list.push({
          file: f,
          projectId: p.id,
          projectName: p.name,
          projectStage: p.stage,
          projectStageLabel: p.stage_label,
        });
      }
    }
    return list;
  }, [projects]);

  // Telemetry metrics
  const telemetry = useMemo(() => {
    const totalFiles = allDatasets.length;
    const totalRows = allDatasets.reduce(
      (acc, d) => acc + d.file.tables.reduce((sum, t) => sum + t.rows, 0),
      0
    );
    const totalSize = allDatasets.reduce((acc, d) => acc + d.file.size_bytes, 0);
    const totalTables = allDatasets.reduce((acc, d) => acc + d.file.tables.length, 0);
    return { totalFiles, totalRows, totalSize, totalTables };
  }, [allDatasets]);

  // Filtered dataset items
  const filtered = useMemo(() => {
    return allDatasets.filter((d) => {
      // Format filter
      const ext = d.file.extension.toLowerCase();
      if (formatFilter === "csv" && !ext.includes("csv")) return false;
      if (formatFilter === "excel" && !(ext.includes("xls") || ext.includes("xlsx"))) return false;

      // Search query
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesName = d.file.filename.toLowerCase().includes(q);
        const matchesProj = d.projectName.toLowerCase().includes(q);
        const matchesTable = d.file.tables.some((t) => t.name.toLowerCase().includes(q));
        return matchesName || matchesProj || matchesTable;
      }
      return true;
    });
  }, [allDatasets, formatFilter, search]);

  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* Header */}
      <section className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-6 border-b border-outline-variant/30">
        <div>
          <span className="font-label-sm text-label-sm text-secondary uppercase tracking-widest font-semibold flex items-center gap-1.5 mb-2">
            <Icon name="storage" size={14} />
            Data Ingestion Hub
          </span>
          <h1 className="font-display-lg text-display-lg text-primary tracking-tight font-medium">
            Datasets & Data Sources
          </h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-1.5 font-light">
            Central repository of all ingested workbooks, tables, and schemas profiled by DashPilot.
          </p>
        </div>

        <PillButton href="/project/upload" arrow>
          Upload New Dataset
        </PillButton>
      </section>

      {/* Telemetry Bento Banner (4 stats) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl p-5 shadow-card border border-outline-variant/20 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center text-primary shrink-0">
            <Icon name="description" size={24} />
          </div>
          <div>
            <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
              INGESTED FILES
            </span>
            <span className="font-display-lg text-headline-lg font-semibold text-primary">
              {telemetry.totalFiles}
            </span>
          </div>
        </div>

        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl p-5 shadow-card border border-outline-variant/20 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center text-secondary shrink-0">
            <Icon name="table_chart" size={24} />
          </div>
          <div>
            <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
              DETECTED TABLES
            </span>
            <span className="font-display-lg text-headline-lg font-semibold text-primary">
              {telemetry.totalTables}
            </span>
          </div>
        </div>

        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl p-5 shadow-card border border-outline-variant/20 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center text-primary shrink-0">
            <Icon name="database" size={24} />
          </div>
          <div>
            <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
              TOTAL RECORDS
            </span>
            <span className="font-display-lg text-headline-lg font-semibold text-primary">
              {telemetry.totalRows.toLocaleString()}
            </span>
          </div>
        </div>

        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl p-5 shadow-card border border-outline-variant/20 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center text-[#2E7D32] shrink-0">
            <Icon name="verified" size={24} />
          </div>
          <div>
            <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold block">
              TOTAL STORAGE
            </span>
            <span className="font-display-lg text-headline-lg font-semibold text-primary">
              {formatBytes(telemetry.totalSize)}
            </span>
          </div>
        </div>
      </section>

      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="relative w-full sm:w-80">
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-on-surface-variant">
            <Icon name="search" size={18} />
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search datasets, tables, or projects..."
            className="w-full pl-10 pr-4 py-2.5 rounded-full bg-surface-container-lowest border border-outline-variant/40 text-[13px] text-primary focus:outline-none focus:border-primary transition-all placeholder:text-on-surface-variant/60 shadow-2xs"
          />
        </div>

        <div className="flex items-center p-1 rounded-full bg-surface-container-low border border-outline-variant/20 self-start sm:self-auto">
          <button
            onClick={() => setFormatFilter("all")}
            className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
              formatFilter === "all"
                ? "bg-surface-container-lowest text-primary shadow-xs"
                : "text-on-surface-variant hover:text-primary"
            }`}
          >
            All Formats ({allDatasets.length})
          </button>
          <button
            onClick={() => setFormatFilter("csv")}
            className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
              formatFilter === "csv"
                ? "bg-surface-container-lowest text-primary shadow-xs"
                : "text-on-surface-variant hover:text-primary"
            }`}
          >
            CSV Files
          </button>
          <button
            onClick={() => setFormatFilter("excel")}
            className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
              formatFilter === "excel"
                ? "bg-surface-container-lowest text-primary shadow-xs"
                : "text-on-surface-variant hover:text-primary"
            }`}
          >
            Excel Workbooks
          </button>
        </div>
      </div>

      {/* Datasets Table */}
      {loading ? (
        <div className="py-24 text-center text-on-surface-variant font-label-md">
          <Icon name="sync" size={24} className="animate-spin mb-2" />
          <p>Scanning data repository...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-20 text-center bg-surface-container-lowest/80 rounded-[28px] border border-outline-variant/20 p-8 shadow-card">
          <div className="w-12 h-12 rounded-full bg-surface-container-low flex items-center justify-center mx-auto mb-3 text-on-surface-variant">
            <Icon name="dataset" size={24} />
          </div>
          <h3 className="font-headline-md text-headline-md font-semibold text-primary mb-1">
            No datasets found
          </h3>
          <p className="text-on-surface-variant text-[13px] max-w-md mx-auto mb-6">
            Upload your CSV or Excel files to let DashPilot profile columns, data types, and null anomalies.
          </p>
          <PillButton href="/project/upload" arrow>
            Upload Dataset
          </PillButton>
        </div>
      ) : (
        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] shadow-card border border-outline-variant/20 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="bg-surface-container-low text-on-surface-variant text-[11px] uppercase tracking-wider font-semibold border-b border-outline-variant/20">
                <tr>
                  <th className="py-3.5 px-6">File Name</th>
                  <th className="py-3.5 px-4">Project</th>
                  <th className="py-3.5 px-4">Tables & Rows</th>
                  <th className="py-3.5 px-4">Size</th>
                  <th className="py-3.5 px-4">Uploaded</th>
                  <th className="py-3.5 px-6 text-right">Quick Jumps</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/15 text-primary">
                {filtered.map((item, idx) => {
                  const f = item.file;
                  const isExcel = f.extension.includes("xls");
                  const totalRows = f.tables.reduce((sum, t) => sum + t.rows, 0);

                  return (
                    <tr
                      key={`${item.projectId}-${f.id}-${idx}`}
                      className="hover:bg-surface-container-low/50 transition-colors"
                    >
                      {/* File Name */}
                      <td className="py-4 px-6 font-medium">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-lg bg-surface-container-low flex items-center justify-center text-primary shrink-0 shadow-2xs">
                            <Icon name={isExcel ? "table_view" : "csv"} size={18} />
                          </div>
                          <div>
                            <span className="font-semibold text-primary block truncate max-w-xs">
                              {f.filename}
                            </span>
                            <span className="text-[11px] text-on-surface-variant">
                              Format: {f.extension.toUpperCase()} · ID: {f.id}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Project Link */}
                      <td className="py-4 px-4">
                        <Link
                          href={`/project/upload?project=${item.projectId}`}
                          className="font-medium text-primary hover:text-secondary truncate block max-w-xs"
                        >
                          {item.projectName}
                        </Link>
                        <span className="text-[11px] text-on-surface-variant">
                          {item.projectStageLabel}
                        </span>
                      </td>

                      {/* Tables & Rows */}
                      <td className="py-4 px-4">
                        <div className="flex flex-wrap items-center gap-1 mb-1">
                          {f.tables.slice(0, 3).map((t, tidx) => (
                            <span
                              key={tidx}
                              className="px-2 py-0.5 rounded-md bg-surface-container-low text-[11px] font-mono font-medium text-primary"
                            >
                              {t.name} ({t.columns} cols)
                            </span>
                          ))}
                          {f.tables.length > 3 && (
                            <span className="text-[10px] text-on-surface-variant font-medium">
                              +{f.tables.length - 3} more
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] text-on-surface-variant block">
                          Total: {totalRows.toLocaleString()} records
                        </span>
                      </td>

                      {/* Size */}
                      <td className="py-4 px-4 text-on-surface-variant text-[12px] font-mono">
                        {formatBytes(f.size_bytes)}
                      </td>

                      {/* Uploaded */}
                      <td className="py-4 px-4 text-on-surface-variant text-[12px]">
                        {timeAgo(f.uploaded_at)}
                      </td>

                      {/* Quick Jumps */}
                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Link
                            href={`/project/upload?project=${item.projectId}`}
                            className="px-2.5 py-1 rounded-full bg-surface-container-low hover:bg-surface-container-high text-[11px] font-medium text-primary transition-colors"
                            title="Profile & Column Health"
                          >
                            Profile
                          </Link>
                          <Link
                            href={`/project/clean?project=${item.projectId}`}
                            className="px-2.5 py-1 rounded-full bg-surface-container-low hover:bg-surface-container-high text-[11px] font-medium text-primary transition-colors"
                            title="Data Cleaning Rules"
                          >
                            Clean
                          </Link>
                          <Link
                            href={`/project/model?project=${item.projectId}`}
                            className="px-2.5 py-1 rounded-full bg-primary text-on-primary hover:opacity-95 text-[11px] font-medium transition-all"
                            title="Star Schema Relationships"
                          >
                            Model
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
