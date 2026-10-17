"use client";

import { useMemo, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { Measure } from "@/lib/api";
import { FORMAT_LABELS, measureIcon, shortDax } from "@/lib/dax";

interface MeasureListProps {
  measures: Measure[];
  folders: Record<string, number>;
  selected: string | null;
  busy: boolean;
  onSelect: (name: string) => void;
  onNew: () => void;
  onValidate: () => void;
}

function StatusPill({ m }: { m: Measure }) {
  if (m.status === "passed") {
    return (
      <span className="px-2.5 py-1 rounded-full bg-surface-container font-label-sm text-label-sm text-on-surface flex items-center gap-1 shrink-0">
        <Icon name="check" className="text-[12px] text-secondary" /> Passed
      </span>
    );
  }
  if (m.status === "edge") {
    return (
      <span className="px-2.5 py-1 rounded-full bg-secondary-container/30 text-secondary font-label-sm text-label-sm font-semibold flex items-center gap-1 shrink-0">
        <Icon name="info" className="text-[12px]" /> Check Edge Cases
      </span>
    );
  }
  return (
    <span className="px-2.5 py-1 rounded-full bg-error-container text-on-error-container font-label-sm text-label-sm font-semibold flex items-center gap-1 shrink-0">
      <Icon name="error" className="text-[12px]" /> Error
    </span>
  );
}

/** Search, folder chips and the folder-grouped measure list. */
export function MeasureList({ measures, folders, selected, busy, onSelect, onNew, onValidate }: MeasureListProps) {
  const [query, setQuery] = useState("");
  const [folder, setFolder] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return measures.filter(
      (m) => (!folder || m.folder === folder) && (!q || m.name.toLowerCase().includes(q) || m.expression.toLowerCase().includes(q)),
    );
  }, [measures, query, folder]);

  const groups = useMemo(() => {
    const map = new Map<string, Measure[]>();
    for (const m of visible) map.set(m.folder, [...(map.get(m.folder) ?? []), m]);
    return [...map.entries()];
  }, [visible]);

  const toggle = (f: string) =>
    setCollapsed((c) => {
      const next = new Set(c);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });

  return (
    <div className="flex flex-col gap-4">
      <div className="p-6 rounded-card bg-surface-container-lowest/80 backdrop-blur-md shadow-card flex flex-col gap-5">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="relative flex-1">
            <Icon name="search" className="absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${measures.length} DAX measures, columns, or syntax...`}
              className="w-full pl-11 pr-4 py-2.5 rounded-full bg-surface-container-low text-on-surface placeholder:text-on-surface-variant text-body-md font-body-md outline-none focus:ring-2 focus:ring-secondary-container transition-all"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onNew}
              className="px-4 py-2.5 rounded-full bg-surface-container-low hover:bg-surface-container text-on-surface font-label-md text-label-md font-medium transition-colors flex items-center gap-1.5"
            >
              <Icon name="add" className="text-[16px]" />
              <span>New Measure</span>
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onValidate}
              className="px-4 py-2.5 rounded-full bg-primary-container text-on-primary font-label-md text-label-md font-medium transition-transform hover:scale-[1.02] flex items-center gap-1.5 disabled:opacity-60"
            >
              <Icon name={busy ? "sync" : "rule"} className={`text-[16px] ${busy ? "animate-spin" : ""}`} />
              <span>Validate All</span>
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            type="button"
            onClick={() => setFolder(null)}
            className={`px-3.5 py-1.5 rounded-full font-label-sm text-label-sm shrink-0 ${folder === null ? "bg-primary-container text-on-primary font-medium" : "bg-surface-container-low text-on-surface-variant hover:text-on-surface"}`}
          >
            All Folders ({measures.length})
          </button>
          {Object.entries(folders).map(([f, n]) => (
            <button
              key={f}
              type="button"
              onClick={() => setFolder(folder === f ? null : f)}
              className={`px-3.5 py-1.5 rounded-full font-label-sm text-label-sm shrink-0 transition-colors ${folder === f ? "bg-secondary-container text-on-secondary-fixed font-semibold" : "bg-surface-container-low text-on-surface-variant hover:text-on-surface"}`}
            >
              {f.replace(" Measures", "")} ({n})
            </button>
          ))}
        </div>
      </div>

      {groups.length === 0 && (
        <p className="px-6 py-8 rounded-card bg-surface-container-lowest/80 shadow-card font-body-md text-body-md text-on-surface-variant">
          No measures match your search.
        </p>
      )}
      {groups.map(([f, items]) => {
        const open = !collapsed.has(f);
        const total = folders[f] ?? items.length;
        return (
          <div key={f} className="rounded-card bg-surface-container-lowest/80 backdrop-blur-md shadow-card overflow-hidden">
            <button type="button" onClick={() => toggle(f)} className="w-full px-6 py-4 bg-surface-container-low/60 flex items-center justify-between">
              <span className="flex items-center gap-2.5">
                <Icon name={open ? "folder_open" : "folder"} className="text-[18px] text-on-surface-variant" />
                <span className="font-title-lg text-title-lg text-on-surface font-semibold tracking-tight">{f}</span>
                <span
                  className={`font-code-sm text-code-sm px-2 py-0.5 rounded-full ${items.some((m) => m.name === selected) ? "bg-secondary-container text-on-surface font-medium" : "bg-surface-container text-on-surface-variant"}`}
                >
                  {items.length === total ? `${total} measure${total === 1 ? "" : "s"}` : `${items.length} shown / ${total}`}
                </span>
              </span>
              <Icon name={open ? "expand_less" : "expand_more"} className="text-[18px] text-on-surface-variant" />
            </button>
            {open && (
              <div className="flex flex-col">
                {items.map((m) => {
                  const active = m.name === selected;
                  return (
                    <button
                      key={m.name}
                      type="button"
                      onClick={() => onSelect(m.name)}
                      className={`relative px-6 py-3.5 flex items-center justify-between gap-3 text-left transition-colors ${active ? "bg-secondary-container/15" : "hover:bg-surface-container-low/40"}`}
                    >
                      {active && <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-secondary-container" />}
                      <span className="flex items-center gap-3 min-w-0">
                        <Icon name={measureIcon(m)} className={`text-[18px] shrink-0 ${active ? "text-secondary" : "text-on-surface-variant"}`} />
                        <span className="flex flex-col min-w-0">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className={`font-title-lg text-title-lg text-on-surface ${active ? "font-semibold" : "font-medium"}`}>[{m.name}]</span>
                            <span className="font-code-sm text-code-sm text-on-surface-variant">
                              {FORMAT_LABELS[m.format]} ({m.format_string})
                            </span>
                            {m.value_text && m.status !== "error" && (
                              <span className="font-code-sm text-code-sm text-on-surface font-medium">= {m.value_text}</span>
                            )}
                          </span>
                          <span className="font-code-sm text-code-sm text-on-surface-variant truncate">{shortDax(m.expression)}</span>
                        </span>
                      </span>
                      <span className="flex items-center gap-3 shrink-0">
                        <StatusPill m={m} />
                        {active ? (
                          <span className="w-7 h-7 rounded-full bg-primary-container text-on-primary flex items-center justify-center">
                            <Icon name="code" className="text-[14px]" />
                          </span>
                        ) : (
                          <Icon name="chevron_right" className="text-[18px] text-on-surface-variant" />
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
