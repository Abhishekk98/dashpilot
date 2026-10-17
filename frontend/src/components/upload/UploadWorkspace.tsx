"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import {
  createProject,
  deleteFile,
  fetchHealth,
  type HealthResponse,
  getProfile,
  getProject,
  profileCsvUrl,
  uploadFiles,
  type Project,
  type QualityReport,
} from "@/lib/api";

import { ColumnProfileTable } from "./ColumnProfileTable";
import { IngestionCard } from "./IngestionCard";
import { ProfileActionBar } from "./ProfileActionBar";
import { QualityReportCard } from "./QualityReportCard";

const MAX_UPLOAD_MB = 100;

/** Step 1 screen state: project in the URL (?project=id), files, and the profiling report. */
export function UploadWorkspace() {
  const router = useRouter();
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [report, setReport] = useState<QualityReport | null>(null);
  const [uploading, setUploading] = useState(false);
  const [profiling, setProfiling] = useState(false);
  // Bumped on every refresh so a slow AI answer for an older file set is ignored.
  const reportRequest = useRef(0);
  const [errors, setErrors] = useState<string[]>([]);
  // null = backend unreachable
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  /** Phase 1: rule-based report (seconds). Phase 2: AI role refinement, shown in place when it lands. */
  const refreshReport = useCallback(async (id: string, p: Project) => {
    const request = ++reportRequest.current;
    const isCurrent = () => request === reportRequest.current;
    if (p.files.length === 0) {
      setReport(null);
      return;
    }
    setProfiling(true);
    let fast: QualityReport;
    try {
      fast = await getProfile(id, false);
      if (!isCurrent()) return;
      setReport(fast);
    } catch (e) {
      if (isCurrent()) setErrors([(e as Error).message]);
      return;
    } finally {
      if (isCurrent()) setProfiling(false);
    }
    if (fast.ai_status !== "pending") return;
    // Not awaited: uploads/removals finish as soon as the rule-based report is on screen.
    getProfile(id, true)
      .then((refined) => isCurrent() && setReport(refined))
      .catch(() => {
        // Keep the rule-based report; mark the AI phase as failed so the badge stops pulsing.
        if (isCurrent()) setReport({ ...fast, ai_status: "failed", ai_note: "AI refinement did not finish" });
      });
  }, []);

  // Load an existing project when the page opens with ?project=...
  useEffect(() => {
    if (!projectId || project?.id === projectId) return;
    getProject(projectId)
      .then((p) => {
        setProject(p);
        return refreshReport(projectId, p);
      })
      .catch(() => {
        setErrors(["That project could not be found. Upload files to start a new one."]);
        router.replace("/project/upload");
      });
  }, [projectId, project?.id, refreshReport, router]);

  const handleFiles = async (files: File[]) => {
    setErrors([]);
    setUploading(true);
    try {
      let current = project;
      if (!current) {
        // Name the project after the first file until the Context step lets users rename it.
        const firstName = files[0]?.name.replace(/\.[^.]+$/, "") ?? "Untitled Project";
        current = await createProject(firstName);
        setProject(current);
        router.replace(`/project/upload?project=${current.id}`);
      }
      const result = await uploadFiles(current.id, files);
      setProject(result.project);
      setErrors(result.errors);
      await refreshReport(current.id, result.project);
    } catch (e) {
      setErrors([(e as Error).message || "Upload failed. Is the backend running?"]);
    } finally {
      setUploading(false);
    }
  };

  const handleRemove = async (fileId: string) => {
    if (!project) return;
    try {
      const updated = await deleteFile(project.id, fileId);
      setProject(updated);
      await refreshReport(updated.id, updated);
    } catch (e) {
      setErrors([(e as Error).message]);
    }
  };

  const providerName = health?.llm_provider === "claude" ? "Claude" : "Gemini";
  const engineLabel = !health
    ? "Backend offline"
    : health.llm_configured
      ? `${providerName} AI Profiler • ${health.llm_model}`
      : `Rule-based Profiling (no ${providerName} key)`;
  const engineDot = !health ? "bg-coral" : health.llm_configured ? "bg-[#107C41]" : "bg-sunflower";

  return (
    <div className="flex flex-col w-full">
      <StepHeader
        step={1}
        title={project?.name ?? "Upload & Profiling"}
        projectId={project?.id}
        badge={project ? "Draft" : undefined}
        status={
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-lowest/90 backdrop-blur-md shadow-sm font-code-sm text-code-sm text-on-surface-variant">
            <span className={`w-2 h-2 rounded-full ${engineDot}`} />
            <span>{engineLabel}</span>
          </span>
        }
      />

      {errors.length > 0 && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <ul className="font-body-md text-body-md">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-8">
        <IngestionCard
          files={project?.files ?? []}
          uploading={uploading}
          maxUploadMb={MAX_UPLOAD_MB}
          onFiles={handleFiles}
          onRemove={handleRemove}
        />
        <QualityReportCard report={report} loading={profiling || uploading} providerName={providerName} />
      </section>

      {report && report.tables.length > 0 && project && (
        <ColumnProfileTable tables={report.tables} csvUrl={profileCsvUrl(project.id)} />
      )}

      <ProfileActionBar report={report} nextHref={project ? `/project/clean?project=${project.id}` : null} />
    </div>
  );
}
