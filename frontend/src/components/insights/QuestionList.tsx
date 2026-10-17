"use client";

import { useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { BusinessQuestion } from "@/lib/api";

interface QuestionListProps {
  questions: BusinessQuestion[];
  selected: string | null;
  onSelect: (q: BusinessQuestion) => void;
  onAsk: () => void;
}

/** Left column: business questions with theme filter and search. */
export function QuestionList({ questions, selected, onSelect, onAsk }: QuestionListProps) {
  const [query, setQuery] = useState("");
  const [theme, setTheme] = useState<string | null>(null);
  const themes = [...new Set(questions.map((q) => q.theme))];
  const q = query.trim().toLowerCase();
  const visible = questions.filter((x) => (!theme || x.theme === theme) && (!q || x.text.toLowerCase().includes(q) || x.answer.toLowerCase().includes(q)));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between px-1">
        <span className="font-title-lg text-title-lg text-on-surface font-semibold">Business Questions Explored</span>
        <span className="px-2 py-0.5 rounded-full bg-surface-container font-code-sm text-code-sm text-on-surface-variant">{questions.length} Core Queries</span>
      </div>
      <div className="relative">
        <Icon name="search" className="absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-[18px]" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search business queries..."
          className="w-full pl-10 pr-4 py-2.5 rounded-full bg-surface-container-lowest/80 text-on-surface placeholder:text-on-surface-variant font-body-md text-body-md outline-none focus:ring-2 focus:ring-secondary-container shadow-sm"
        />
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {[null, ...themes].map((t) => (
          <button
            key={t ?? "all"}
            type="button"
            onClick={() => setTheme(t)}
            className={`px-3 py-1 rounded-full font-label-sm text-label-sm ${theme === t ? "bg-primary-container text-on-primary" : "bg-surface-container-lowest/80 text-on-surface-variant hover:text-on-surface"}`}
          >
            {t ?? "All Themes"}
          </button>
        ))}
      </div>
      {visible.map((x, i) => {
        const active = x.id === selected;
        return (
          <button
            key={x.id}
            type="button"
            onClick={() => onSelect(x)}
            className={`relative p-5 rounded-panel text-left flex flex-col gap-2 transition-all ${active ? "bg-surface-container-lowest shadow-card" : "bg-surface-container-lowest/60 hover:bg-surface-container-lowest/90"}`}
          >
            {active && <span className="absolute left-0 top-4 bottom-4 w-1.5 rounded-r-full bg-secondary-container" />}
            <span className="flex items-start gap-3">
              <span className={`w-7 h-7 rounded-full flex items-center justify-center font-code-sm text-code-sm shrink-0 ${active ? "bg-secondary-container text-on-secondary-fixed font-semibold" : "bg-surface-container text-on-surface-variant"}`}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="font-title-lg text-title-lg text-on-surface font-medium leading-snug">{x.text}</span>
            </span>
            <span className="pl-10 font-body-md text-xs text-on-surface-variant leading-relaxed line-clamp-3">{x.answer}</span>
            <span className="pl-10 flex flex-wrap items-center gap-2 font-code-sm text-[10px] text-on-surface-variant">
              <span className={`px-2 py-0.5 rounded-full ${x.insight_ids.length ? "bg-secondary-container/40 text-on-secondary-container" : "bg-surface-container"}`}>
                {x.insight_ids.length} {x.insight_ids.length === 1 ? "Insight" : "Insights"} Linked
              </span>
              <span>Theme: {x.theme}</span>
              {x.source === "ai" && <span>• AI question</span>}
            </span>
          </button>
        );
      })}
      <button
        type="button"
        onClick={onAsk}
        className="p-3.5 rounded-full bg-surface-container-lowest/80 hover:bg-surface-container-lowest shadow-sm font-label-md text-label-md text-on-surface flex items-center justify-center gap-2"
      >
        <Icon name="psychology" className="text-[18px] text-secondary" />+ Ask Custom Natural Language Question
      </button>
    </div>
  );
}
