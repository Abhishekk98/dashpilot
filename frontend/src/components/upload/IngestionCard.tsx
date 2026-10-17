"use client";

import { useRef, useState, type DragEvent } from "react";

import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PillTag } from "@/components/ui/PillTag";
import type { StoredFile } from "@/lib/api";
import { formatBytes, formatNumber, timeAgo } from "@/lib/format";

const ACCEPT = ".csv,.xlsx,.xls";

const FILE_ICONS: Record<string, { icon: string; box: string }> = {
  ".csv": { icon: "table_chart", box: "bg-secondary-container/40 text-on-secondary-container" },
  ".xlsx": { icon: "description", box: "bg-[#D2E3FC] text-[#174EA6]" },
  ".xls": { icon: "description", box: "bg-[#D2E3FC] text-[#174EA6]" },
};

interface IngestionCardProps {
  files: StoredFile[];
  uploading: boolean;
  maxUploadMb: number;
  onFiles: (files: File[]) => void;
  onRemove: (fileId: string) => void;
}

/** Left card of the Upload screen: drop zone + "Active Session Tables" list. */
export function IngestionCard({ files, uploading, maxUploadMb, onFiles, onRemove }: IngestionCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const tableCount = files.reduce((n, f) => n + f.tables.length, 0);

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) onFiles(Array.from(e.dataTransfer.files));
  };

  return (
    <div className="lg:col-span-7 flex flex-col justify-between rounded-card bg-surface-container-lowest/70 backdrop-blur-xl p-7 shadow-card">
      <div>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Icon name="file_upload" className="text-[20px] text-primary-container" />
            <span className="font-title-lg text-title-lg font-semibold text-on-surface">Data Ingestion Hub</span>
          </div>
          <PillTag mono size="md">
            {files.length} {files.length === 1 ? "File" : "Files"} • {tableCount} {tableCount === 1 ? "Table" : "Tables"}
          </PillTag>
        </div>

        {/* Drop zone: the whole area is clickable and accepts drag & drop. */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => !uploading && inputRef.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`relative group cursor-pointer rounded-panel transition-all duration-300 p-8 flex flex-col items-center justify-center text-center focus-halo ${
            dragging
              ? "bg-secondary-container/20 shadow-[inset_0_0_0_2px_#F8CF4B]"
              : "bg-surface-container-lowest/60 hover:bg-surface-container-lowest/90 shadow-[inset_0_0_0_1.5px_#D9D9D6]"
          }`}
        >
          <div className="w-14 h-14 rounded-full bg-surface-container flex items-center justify-center text-on-surface group-hover:scale-105 transition-transform duration-300 shadow-sm mb-4">
            <Icon name="cloud_upload" className="text-[28px] text-on-surface" />
          </div>
          <h2 className="font-headline-lg text-headline-lg font-semibold text-on-surface tracking-tight mb-1">
            Drop CSV or Excel files
          </h2>
          <p className="font-body-md text-body-md text-on-surface-variant max-w-md mx-auto mb-5 leading-relaxed">
            DashPilot automatically detects relational keys, date hierarchies, and column semantic roles. Supports{" "}
            <span className="font-code-md text-on-surface font-medium">.csv</span>,{" "}
            <span className="font-code-md text-on-surface font-medium">.xlsx</span>,{" "}
            <span className="font-code-md text-on-surface font-medium">.xls</span> up to {maxUploadMb} MB each.
          </p>
          {uploading ? (
            <div className="w-64 flex flex-col gap-2" aria-live="polite">
              <div className="h-2 rounded-full bg-hatched animate-pulse" />
              <span className="font-code-sm text-code-sm text-on-surface-variant">Uploading & profiling…</span>
            </div>
          ) : (
            <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
              <PillButton icon="folder_open" onClick={() => inputRef.current?.click()}>
                Browse Local Files
              </PillButton>
              <PillButton variant="secondary" icon="link" disabled title="Coming soon">
                Cloud Storage
              </PillButton>
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files?.length) onFiles(Array.from(e.target.files));
              e.target.value = ""; // allow re-selecting the same file
            }}
          />
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-2.5">
        <div className="flex items-center justify-between px-1">
          <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-semibold">
            Active Session Tables
          </span>
          <span className="font-code-sm text-code-sm text-on-surface-variant">Stored in project workspace</span>
        </div>
        {files.length === 0 && (
          <p className="px-1 py-3 font-body-md text-body-md text-on-surface-variant">No files yet.</p>
        )}
        {files.map((file) => {
          const style = FILE_ICONS[file.extension] ?? FILE_ICONS[".csv"];
          const rows = file.tables.reduce((n, t) => n + t.rows, 0);
          return (
            <div
              key={file.id}
              className="flex items-center justify-between p-3.5 rounded-inner bg-surface-container-lowest/80 backdrop-blur-md shadow-[0_2px_12px_-2px_rgba(35,35,35,0.03)] hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 ${style.box}`}>
                  <Icon name={style.icon} className="text-[20px]" />
                </div>
                <div className="flex flex-col min-w-0">
                  <div className="flex items-center gap-2 truncate">
                    <span className="font-body-md text-body-md font-semibold text-on-surface truncate">{file.filename}</span>
                    <PillTag tone="success">
                      <Icon name="check" className="text-[13px]" />
                      Parsed
                    </PillTag>
                  </div>
                  <span className="font-code-sm text-code-sm text-on-surface-variant">
                    {formatBytes(file.size_bytes)} • {formatNumber(rows)} rows
                    {file.tables.length > 1 && ` • ${file.tables.length} sheets`} • Uploaded {timeAgo(file.uploaded_at)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                title="Remove table"
                aria-label={`Remove ${file.filename}`}
                onClick={() => onRemove(file.id)}
                className="w-8 h-8 rounded-full flex items-center justify-center text-on-surface-variant hover:text-error hover:bg-error-container/40 transition-colors ml-2 shrink-0"
              >
                <Icon name="close" className="text-[18px]" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
