"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { getInsights, getProject, type InsightPlan, type Project } from "@/lib/api";

import { InsightChart } from "./InsightChart";
import { TYPE_LABELS } from "./InsightCard";

/** A plain, printable summary of questions and insights (pinned ones first). */
export function InsightsPrint() {
  const projectId = useSearchParams().get("project");
  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<InsightPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([getProject(projectId), getInsights(projectId, false)])
      .then(([p, i]) => {
        setProject(p);
        setPlan(i);
      })
      .catch((e) => setError((e as Error).message));
  }, [projectId]);

  if (!projectId) return <p className="p-8">No project selected.</p>;
  if (error) return <p className="p-8 text-error">{error}</p>;
  if (!plan) return <p className="p-8 text-on-surface-variant">Preparing the report…</p>;

  const ordered = [...plan.insights].sort((a, b) => Number(b.pinned) - Number(a.pinned));
  return (
    <div className="max-w-3xl mx-auto bg-surface-container-lowest p-10 rounded-card print:rounded-none print:p-0 print:shadow-none shadow-card text-on-surface">
      <div className="flex items-start justify-between gap-4 mb-6 print:hidden">
        <p className="font-body-md text-body-md text-on-surface-variant">Use your browser&apos;s print dialog and choose “Save as PDF”.</p>
        <button
          type="button"
          onClick={() => window.print()}
          className="px-4 py-2 rounded-full bg-primary-container text-on-primary font-label-md text-label-md flex items-center gap-1.5 shrink-0"
        >
          <Icon name="print" className="text-[16px]" /> Print / Save as PDF
        </button>
      </div>
      <header className="mb-8">
        <p className="font-code-sm text-code-sm uppercase tracking-wider text-on-surface-variant">DashPilot • Insights Summary</p>
        <h1 className="font-headline-xl text-headline-xl font-light tracking-tight">{project?.name ?? "Project"}</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          {plan.insights.length} insights from {plan.rows_scanned.toLocaleString("en-US")} rows • every number computed from the cleaned data • generated{" "}
          {new Date().toLocaleDateString()}
        </p>
      </header>

      <section className="mb-8 break-inside-avoid">
        <h2 className="font-headline-md text-headline-md font-semibold mb-3">Business questions</h2>
        <ol className="flex flex-col gap-3 list-decimal pl-5">
          {plan.questions.map((q) => (
            <li key={q.id} className="font-body-md text-body-md">
              <span className="font-semibold">{q.text}</span>
              <br />
              <span className="text-on-surface-variant">{q.answer}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="flex flex-col gap-6">
        <h2 className="font-headline-md text-headline-md font-semibold">Insights</h2>
        {ordered.map((i) => (
          <article key={i.id} className="break-inside-avoid border-t border-surface-container pt-4 flex flex-col gap-2">
            <p className="font-code-sm text-code-sm uppercase text-on-surface-variant">
              {TYPE_LABELS[i.type]}
              {i.pinned ? " • Pinned for the dashboard" : ""}
            </p>
            <h3 className="font-title-lg text-title-lg font-semibold">{i.headline}</h3>
            <p className="font-body-md text-body-md text-on-surface-variant">{i.body}</p>
            <div className="max-w-md">
              <InsightChart insight={i} />
            </div>
            <p className="font-body-md text-body-md">
              <span className="font-semibold">Recommended action: </span>
              {i.action}
            </p>
          </article>
        ))}
      </section>
    </div>
  );
}
