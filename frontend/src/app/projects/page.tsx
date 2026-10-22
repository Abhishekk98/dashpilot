"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { listProjects, deleteProject, ProjectSummary } from "@/lib/api";
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

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "ready" | "in_flight" | "draft">("all");
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = () => {
    setLoading(true);
    listProjects()
      .then((data) => setProjects(data))
      .catch((err) => console.error("Failed to load projects", err))
      .finally(() => setLoading(false));
  };

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Are you sure you want to delete "${name}"? This action cannot be undone.`)) {
      return;
    }
    setDeletingId(id);
    try {
      await deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      alert("Failed to delete project: " + err);
    } finally {
      setDeletingId(null);
    }
  };

  const filtered = useMemo(() => {
    return projects.filter((p) => {
      // Filter tab
      if (filter === "ready" && !p.has_build) return false;
      if (filter === "in_flight" && (p.has_build || p.stage === 1)) return false;
      if (filter === "draft" && p.stage > 1) return false;

      // Search query
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesName = p.name.toLowerCase().includes(q);
        const matchesIndustry = p.industry?.toLowerCase().includes(q);
        const matchesStage = p.stage_label.toLowerCase().includes(q);
        return matchesName || matchesIndustry || matchesStage;
      }
      return true;
    });
  }, [projects, filter, search]);

  const counts = useMemo(() => {
    return {
      all: projects.length,
      ready: projects.filter((p) => p.has_build).length,
      in_flight: projects.filter((p) => !p.has_build && p.stage > 1).length,
      draft: projects.filter((p) => p.stage === 1).length,
    };
  }, [projects]);

  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* Header */}
      <section className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-6 border-b border-outline-variant/30">
        <div>
          <span className="font-label-sm text-label-sm text-secondary uppercase tracking-widest font-semibold flex items-center gap-1.5 mb-2">
            <Icon name="workspaces" size={14} />
            Project Hub
          </span>
          <h1 className="font-display-lg text-display-lg text-primary tracking-tight font-medium">
            Projects Workspace
          </h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-1.5 font-light">
            Manage, resume workflows, and export Power BI Desktop templates (.pbip) for your enterprise datasets.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <PillButton href="/project/upload" arrow>
            New Project
          </PillButton>
        </div>
      </section>

      {/* Controls Bar: Search, Filters, View Toggle */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Search Input */}
        <div className="relative w-full md:w-80">
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-on-surface-variant">
            <Icon name="search" size={18} />
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search projects or industries..."
            className="w-full pl-10 pr-4 py-2.5 rounded-full bg-surface-container-lowest border border-outline-variant/40 text-[13px] text-primary focus:outline-none focus:border-primary transition-all placeholder:text-on-surface-variant/60 shadow-2xs"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary text-[14px]"
            >
              ×
            </button>
          )}
        </div>

        {/* Filter Pills & View Toggle */}
        <div className="flex flex-wrap items-center justify-between md:justify-end gap-3 w-full md:w-auto">
          {/* Tabs */}
          <div className="flex items-center p-1 rounded-full bg-surface-container-low border border-outline-variant/20">
            <button
              onClick={() => setFilter("all")}
              className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
                filter === "all"
                  ? "bg-surface-container-lowest text-primary shadow-xs"
                  : "text-on-surface-variant hover:text-primary"
              }`}
            >
              All ({counts.all})
            </button>
            <button
              onClick={() => setFilter("ready")}
              className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
                filter === "ready"
                  ? "bg-surface-container-lowest text-primary shadow-xs"
                  : "text-on-surface-variant hover:text-primary"
              }`}
            >
              Ready ({counts.ready})
            </button>
            <button
              onClick={() => setFilter("in_flight")}
              className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
                filter === "in_flight"
                  ? "bg-surface-container-lowest text-primary shadow-xs"
                  : "text-on-surface-variant hover:text-primary"
              }`}
            >
              In Flight ({counts.in_flight})
            </button>
            <button
              onClick={() => setFilter("draft")}
              className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-all ${
                filter === "draft"
                  ? "bg-surface-container-lowest text-primary shadow-xs"
                  : "text-on-surface-variant hover:text-primary"
              }`}
            >
              Drafts ({counts.draft})
            </button>
          </div>

          {/* Grid/Table View Mode */}
          <div className="flex items-center p-1 rounded-full bg-surface-container-low border border-outline-variant/20">
            <button
              onClick={() => setViewMode("grid")}
              className={`p-1.5 rounded-full transition-all ${
                viewMode === "grid"
                  ? "bg-surface-container-lowest text-primary shadow-xs"
                  : "text-on-surface-variant hover:text-primary"
              }`}
              title="Grid View"
              aria-label="Grid View"
            >
              <Icon name="grid_view" size={16} />
            </button>
            <button
              onClick={() => setViewMode("table")}
              className={`p-1.5 rounded-full transition-all ${
                viewMode === "table"
                  ? "bg-surface-container-lowest text-primary shadow-xs"
                  : "text-on-surface-variant hover:text-primary"
              }`}
              title="Table View"
              aria-label="Table View"
            >
              <Icon name="table_rows" size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Projects Display */}
      {loading ? (
        <div className="py-24 text-center text-on-surface-variant font-label-md">
          <Icon name="sync" size={24} className="animate-spin mb-2" />
          <p>Loading projects...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-20 text-center bg-surface-container-lowest/80 rounded-[28px] border border-outline-variant/20 p-8 shadow-card">
          <div className="w-12 h-12 rounded-full bg-surface-container-low flex items-center justify-center mx-auto mb-3 text-on-surface-variant">
            <Icon name="folder_open" size={24} />
          </div>
          <h3 className="font-headline-md text-headline-md font-semibold text-primary mb-1">
            No projects found
          </h3>
          <p className="text-on-surface-variant text-[13px] max-w-md mx-auto mb-6">
            {search
              ? `No projects match "${search}". Try resetting your search or filter.`
              : "No projects exist in this category yet. Start your first analytical project."}
          </p>
          <PillButton href="/project/upload" arrow>
            Start New Project
          </PillButton>
        </div>
      ) : viewMode === "grid" ? (
        /* GRID VIEW */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((proj) => {
            const isDeleting = deletingId === proj.id;
            return (
              <div
                key={proj.id}
                className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] p-6 shadow-card hover:shadow-card-hover transition-all duration-300 border border-outline-variant/20 flex flex-col justify-between group"
              >
                <div>
                  {/* Top Badges */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
                        proj.has_build
                          ? "bg-[#E8F5E9] text-[#2E7D32]"
                          : proj.stage >= 6
                          ? "bg-secondary-container text-on-secondary-fixed"
                          : "bg-surface-container-high text-on-surface-variant"
                      }`}
                    >
                      {proj.stage_label}
                    </span>

                    <span className="text-[11px] font-medium text-on-surface-variant">
                      Stage {proj.stage}/9
                    </span>
                  </div>

                  {/* Project Name */}
                  <h3 className="font-headline-md text-headline-md font-semibold text-primary mb-2 line-clamp-1 group-hover:text-secondary transition-colors">
                    <Link href={getStageUrl(proj.id, proj.stage)}>{proj.name}</Link>
                  </h3>

                  {/* Metadata Chips */}
                  <div className="flex flex-wrap items-center gap-2 mb-4 text-[11px] text-on-surface-variant">
                    {proj.industry && (
                      <span className="px-2 py-0.5 rounded-full bg-surface-container-low font-medium text-primary">
                        {proj.industry}
                      </span>
                    )}
                    <span>{proj.files_count} file(s)</span>
                    <span>·</span>
                    <span>{proj.tables_count} table(s)</span>
                    <span>·</span>
                    <span>{formatBytes(proj.size_bytes)}</span>
                  </div>

                  {/* Progress Bar across 9 stages */}
                  <div className="mb-5">
                    <div className="flex justify-between text-[11px] text-on-surface-variant mb-1 font-medium">
                      <span>Pipeline Progress</span>
                      <span>{Math.round((proj.stage / 9) * 100)}%</span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-surface-container-high overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          proj.has_build ? "bg-[#2E7D32]" : "bg-primary"
                        }`}
                        style={{ width: `${(proj.stage / 9) * 100}%` }}
                      />
                    </div>
                  </div>

                  {/* Stats snippet */}
                  <div className="grid grid-cols-2 gap-2 p-3 rounded-2xl bg-surface-container-low/60 mb-5 border border-outline-variant/15 text-[12px]">
                    <div>
                      <span className="text-[10px] uppercase text-on-surface-variant font-semibold block">
                        PAGES
                      </span>
                      <span className="font-semibold text-primary">{proj.pages_count} Page(s)</span>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase text-on-surface-variant font-semibold block">
                        MEASURES
                      </span>
                      <span className="font-semibold text-primary">
                        {proj.measures_count ? `${proj.measures_count} DAX` : "In Progress"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Card Actions */}
                <div className="flex items-center justify-between gap-2 pt-3 border-t border-outline-variant/15">
                  <span className="text-[11px] text-on-surface-variant font-medium">
                    Updated {timeAgo(proj.updated_at)}
                  </span>

                  <div className="flex items-center gap-1.5">
                    {proj.has_build && (
                      <a
                        href={`http://127.0.0.1:8000/api/projects/${proj.id}/build/download`}
                        download
                        className="p-2 rounded-full bg-surface-container-low hover:bg-surface-container-high text-primary transition-colors"
                        title="Download Power BI Project (.pbip ZIP)"
                      >
                        <Icon name="download" size={16} />
                      </a>
                    )}
                    <button
                      onClick={() => handleDelete(proj.id, proj.name)}
                      disabled={isDeleting}
                      className="p-2 rounded-full bg-surface-container-low hover:bg-red-50 text-on-surface-variant hover:text-red-600 transition-colors"
                      title="Delete Project"
                      aria-label="Delete Project"
                    >
                      <Icon name="delete" size={16} />
                    </button>
                    <Link
                      href={getStageUrl(proj.id, proj.stage)}
                      className="px-3.5 py-1.5 rounded-full bg-primary text-on-primary hover:opacity-95 transition-all text-[12px] font-medium flex items-center gap-1"
                    >
                      <span>{proj.has_build ? "View" : "Resume"}</span>
                      <Icon name="arrow_forward" size={14} />
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* TABLE VIEW */
        <div className="bg-surface-container-lowest/90 backdrop-blur-md rounded-[28px] shadow-card border border-outline-variant/20 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="bg-surface-container-low text-on-surface-variant text-[11px] uppercase tracking-wider font-semibold border-b border-outline-variant/20">
                <tr>
                  <th className="py-3.5 px-6">Project</th>
                  <th className="py-3.5 px-4">Stage</th>
                  <th className="py-3.5 px-4">Data Source</th>
                  <th className="py-3.5 px-4">Pages / DAX</th>
                  <th className="py-3.5 px-4">Updated</th>
                  <th className="py-3.5 px-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/15 text-primary">
                {filtered.map((proj) => (
                  <tr key={proj.id} className="hover:bg-surface-container-low/50 transition-colors">
                    <td className="py-4 px-6 font-medium">
                      <Link
                        href={getStageUrl(proj.id, proj.stage)}
                        className="hover:text-secondary font-semibold block truncate max-w-xs"
                      >
                        {proj.name}
                      </Link>
                      <span className="text-[11px] text-on-surface-variant">
                        ID: {proj.id.slice(0, 8)} {proj.industry ? `· ${proj.industry}` : ""}
                      </span>
                    </td>
                    <td className="py-4 px-4">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
                          proj.has_build
                            ? "bg-[#E8F5E9] text-[#2E7D32]"
                            : proj.stage >= 6
                            ? "bg-secondary-container text-on-secondary-fixed"
                            : "bg-surface-container-high text-on-surface-variant"
                        }`}
                      >
                        {proj.stage_label}
                      </span>
                    </td>
                    <td className="py-4 px-4 text-on-surface-variant text-[12px]">
                      <span>{proj.files_count} file(s)</span> · <span>{formatBytes(proj.size_bytes)}</span>
                      <span className="block text-[11px]">{proj.rows_total.toLocaleString()} rows</span>
                    </td>
                    <td className="py-4 px-4 text-[12px]">
                      <span>{proj.pages_count} Page(s)</span>
                      <span className="block text-[11px] text-on-surface-variant">
                        {proj.measures_count} measures
                      </span>
                    </td>
                    <td className="py-4 px-4 text-on-surface-variant text-[12px]">
                      {timeAgo(proj.updated_at)}
                    </td>
                    <td className="py-4 px-6 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {proj.has_build && (
                          <a
                            href={`http://127.0.0.1:8000/api/projects/${proj.id}/build/download`}
                            download
                            className="p-1.5 rounded-full hover:bg-surface-container-high text-primary transition-colors"
                            title="Download .pbip"
                          >
                            <Icon name="download" size={16} />
                          </a>
                        )}
                        <button
                          onClick={() => handleDelete(proj.id, proj.name)}
                          className="p-1.5 rounded-full hover:bg-red-50 text-on-surface-variant hover:text-red-600 transition-colors"
                          title="Delete Project"
                        >
                          <Icon name="delete" size={16} />
                        </button>
                        <Link
                          href={getStageUrl(proj.id, proj.stage)}
                          className="px-3 py-1 rounded-full bg-primary text-on-primary hover:opacity-95 transition-all text-[12px] font-medium"
                        >
                          Open
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
