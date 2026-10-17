"use client";

import { type ReactNode, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { TableCleaning } from "@/lib/api";

const KEYWORDS = new Set(["let", "in", "each", "if", "then", "else", "type", "null", "true", "false", "and", "or", "not"]);
// Comments, quoted identifiers (#"..."), strings and words, in that order of precedence.
const TOKEN = /(\/\/[^\n]*)|(#"(?:[^"]|"")*")|("(?:[^"]|"")*")|([A-Za-z_][A-Za-z0-9_.]*)/g;

/** Minimal Power Query M highlighter using the design's code colours. */
function highlight(code: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of code.matchAll(TOKEN)) {
    const [text, comment, ident, str, word] = m;
    const i = m.index ?? 0;
    if (i > last) out.push(code.slice(last, i));
    if (comment) out.push(<span key={i} className="text-on-primary-container">{text}</span>);
    else if (ident) out.push(<span key={i}>#<span className="text-[#90CAF9]">{ident.slice(1)}</span></span>);
    else if (str) out.push(<span key={i} className="text-[#A5D6A7]">{text}</span>);
    else if (word && KEYWORDS.has(word))
      out.push(<span key={i} className={`text-secondary-container ${word === "let" || word === "in" ? "font-semibold" : ""}`}>{text}</span>);
    else out.push(text);
    last = i + text.length;
  }
  out.push(code.slice(last));
  return out;
}

/** Dark "Power Query (M) Formula Engine" card with copy and collapse. */
export function MScriptCard({ tables, accepted }: { tables: TableCleaning[]; accepted: number }) {
  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);
  const script = tables.map((t) => t.m_script).join("\n\n");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(script);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="rounded-card bg-primary-container text-on-primary p-6 shadow-dark relative overflow-hidden flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-surface-container-lowest/10 flex items-center justify-center text-secondary-container shrink-0">
            <Icon name="data_object" className="text-[18px]" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-title-lg text-title-lg text-on-primary font-medium tracking-tight">Power Query (M) Formula Engine</span>
              <span className="px-2 py-0.5 rounded-full bg-surface-container-lowest/15 text-secondary-container font-code-sm text-code-sm">
                {accepted} {accepted === 1 ? "step" : "steps"} staged
              </span>
            </div>
            <p className="font-label-sm text-label-sm text-on-primary-container truncate">
              Auto-compiled deterministic script • {tables.map((t) => t.source).join(", ")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={copy}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-container-lowest/10 hover:bg-surface-container-lowest/20 text-on-primary font-label-md text-label-md transition-colors"
          >
            <Icon name={copied ? "check" : "content_copy"} className="text-[15px]" />
            <span>{copied ? "Copied" : "Copy Script"}</span>
          </button>
          <button
            type="button"
            aria-label={collapsed ? "Expand script" : "Collapse script"}
            onClick={() => setCollapsed((c) => !c)}
            className="w-8 h-8 rounded-full bg-surface-container-lowest/10 hover:bg-surface-container-lowest/20 flex items-center justify-center text-on-primary transition-colors"
          >
            <Icon name={collapsed ? "unfold_more" : "unfold_less"} className="text-[18px]" />
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="w-full bg-[#1A1A1A] rounded-2xl p-4 overflow-auto max-h-[560px] font-code-md text-code-md leading-relaxed selection:bg-secondary-container selection:text-on-secondary-fixed">
          <pre className="text-[#E0E0E0]">
            <code>{highlight(script)}</code>
          </pre>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 text-on-primary-container font-code-sm text-code-sm pt-1">
        <span>Set the DataFolder parameter to repoint the source in Power BI</span>
        <span className="flex items-center gap-1 text-secondary-container">
          <Icon name="bolt" className="text-[14px]" />
          Runs on every refresh
        </span>
      </div>
    </div>
  );
}
