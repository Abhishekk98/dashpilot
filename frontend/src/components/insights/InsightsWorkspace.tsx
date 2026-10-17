"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { StepHeader } from "@/components/layout/StepHeader";
import { Icon } from "@/components/ui/Icon";
import { PillButton } from "@/components/ui/PillButton";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";
import {
  askQuestion,
  type BusinessQuestion,
  deleteAsked,
  getInsights,
  getProject,
  type Insight,
  type InsightPlan,
  pinInsight,
  type Project,
} from "@/lib/api";
import { formatNumber } from "@/lib/format";

import { InsightCard, TYPE_LABELS } from "./InsightCard";
import { NorthStarCard } from "./NorthStarCard";
import { QuestionList } from "./QuestionList";

/** Step 6 screen state: computed insights, questions, AI phrasing (phase 2), pins and custom questions. */
export function InsightsWorkspace() {
  const projectId = useSearchParams().get("project");

  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<InsightPlan | null>(null);
  const [type, setType] = useState<Insight["type"] | null>(null);
  const [question, setQuestion] = useState<BusinessQuestion | null>(null);
  const [asking, setAsking] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [askText, setAskText] = useState("");
  const [lastAnswer, setLastAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [narrating, setNarrating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const askRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    Promise.all([getProject(projectId), getInsights(projectId, false)])
      .then(([p, plan]) => {
        if (!alive) return;
        setProject(p);
        setPlan(plan);
        if ((plan.ai_status === "available" || plan.ai_status === "failed") && plan.insights.length) {
          // Phase 2: the LLM phrases the computed facts once; numbers are grounded on the server.
          setNarrating(true);
          getInsights(projectId, true)
            .then((refined) => alive && setPlan(refined))
            .catch(() => undefined)
            .finally(() => alive && setNarrating(false));
        }
      })
      .catch((e) => setError((e as Error).message || "Could not compute insights. Is the backend running?"));
    return () => {
      alive = false;
    };
  }, [projectId]);

  const run = useCallback(async (action: () => Promise<InsightPlan>) => {
    setBusy(true);
    try {
      setPlan(await action());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  if (!projectId) {
    return (
      <div className="flex flex-col w-full">
        <StepHeader step={6} title="AI Insights" />
        <PlaceholderCard icon="upload_file" title="No project selected" description="Upload data and build measures first; insights are computed from them." />
        <Link href="/project/upload" className="mt-6 self-center font-label-md text-label-md underline underline-offset-4 text-on-surface-variant hover:text-on-surface">
          Go to Step 1: Upload
        </Link>
      </div>
    );
  }

  const ask = async () => {
    if (!askText.trim()) return;
    setAsking(true);
    setError(null);
    try {
      const res = await askQuestion(projectId, askText);
      setPlan(res.plan);
      setLastAnswer(res.asked.insight.id);
      setType(null);
      setQuestion(null);
      setAskText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAsking(false);
    }
  };

  const insights = plan?.insights ?? [];
  const north = insights.find((i) => i.id === plan?.north_star) ?? null;
  const counts = insights.reduce<Record<string, number>>((acc, i) => ({ ...acc, [i.type]: (acc[i.type] ?? 0) + 1 }), {});
  const others = insights
    .filter((i) => i.id !== north?.id)
    .filter((i) => !type || i.type === type)
    .filter((i) => !question || question.insight_ids.includes(i.id))
    .sort((a, b) => Number(b.id === lastAnswer) - Number(a.id === lastAnswer));
  const alerts = insights.filter((i) => i.type === "anomaly" || i.type === "rate_alert").length;
  const togglePin = (i: Insight) => run(() => pinInsight(projectId, i.id, !i.pinned));

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={6} title={project?.name ?? "AI Insights"} projectId={projectId} badge={project ? "Draft" : undefined} />

      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-8">
        <div className="flex flex-col gap-2 max-w-2xl">
          <span className="inline-flex items-center gap-2 w-fit px-3 py-1 rounded-full bg-surface-container-lowest/80 font-code-sm text-code-sm uppercase tracking-wider text-on-surface-variant">
            <span className="w-2 h-2 rounded-full bg-secondary-container" /> AI Synthesis Engine • Narrative &amp; Anomaly Detection
          </span>
          <h1 className="font-headline-xl text-headline-xl text-on-surface font-light tracking-tight">Automated Insights &amp; Business Intelligence</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            {plan
              ? `DashPilot scanned ${formatNumber(plan.rows_scanned)} rows across ${plan.dimensions.length} dimensions to answer core business questions and surface anomalies. Every number is computed from your cleaned data.`
              : "Computing insights from your measures…"}
          </p>
        </div>
        {plan && (
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-secondary-container/40 font-label-md text-label-md text-on-surface">
              <Icon name="auto_awesome" className="text-[16px] text-secondary" /> {insights.length} Key Insights Generated
            </span>
            <span className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-surface-container-lowest/80 font-label-md text-label-md text-on-surface">
              <Icon name="verified" className="text-[16px] text-secondary" /> Model Confidence: {(plan.confidence * 100).toFixed(1)}%
            </span>
            <span className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-surface-container-lowest/80 font-label-md text-label-md text-on-surface" title={plan.ai_note ?? undefined}>
              <Icon name={narrating ? "sync" : "fact_check"} className={`text-[16px] ${narrating ? "animate-spin" : ""}`} />
              {narrating ? "AI writing narratives…" : plan.ai_status === "done" ? "Narratives grounded" : plan.ai_status === "failed" ? "Computed narratives (AI unavailable)" : "Computed narratives"}
            </span>
          </div>
        )}
      </section>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-inner bg-error-container/60 text-on-error-container flex items-start gap-3">
          <Icon name="error" className="text-[20px] mt-0.5" />
          <span className="font-body-md text-body-md">{error}</span>
        </div>
      )}
      {plan && (plan.notes.length > 0 || (plan.ai_status === "done" && plan.ai_note)) && (
        <div role="status" className="mb-6 p-4 rounded-inner bg-surface-container-lowest/80 shadow-card flex flex-col gap-1.5">
          {[...plan.notes, ...(plan.ai_note && plan.ai_status === "done" ? [plan.ai_note] : [])].map((n) => (
            <p key={n} className="flex items-start gap-2 font-body-md text-xs text-on-surface">
              <Icon name="info" className="text-[16px] text-secondary shrink-0" />
              <span>{n}</span>
            </p>
          ))}
        </div>
      )}

      {!plan && !error && <div className="h-96 rounded-card bg-hatched animate-pulse mb-8" />}
      {plan && insights.length === 0 && (
        <PlaceholderCard icon="query_stats" title="No insights yet" description="Add measures in KPIs & DAX (at least one sum or count over the fact table) to compute insights." />
      )}

      {plan && insights.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start mb-8">
          <div className="lg:col-span-4">
            <QuestionList
              questions={plan.questions}
              selected={question?.id ?? null}
              onSelect={(q) => {
                setQuestion(question?.id === q.id ? null : q);
                setType(null);
              }}
              onAsk={() => {
                setAskOpen(true);
                setTimeout(() => askRef.current?.focus(), 0);
              }}
            />
          </div>

          <div className="lg:col-span-8 flex flex-col gap-5">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setType(null);
                  setQuestion(null);
                }}
                className={`px-3.5 py-1.5 rounded-full font-label-sm text-label-sm ${!type && !question ? "bg-primary-container text-on-primary" : "bg-surface-container-lowest/80 text-on-surface-variant hover:text-on-surface"}`}
              >
                All Insights ({insights.length})
              </button>
              {(Object.keys(TYPE_LABELS) as Insight["type"][]).filter((t) => counts[t]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => {
                    setType(type === t ? null : t);
                    setQuestion(null);
                  }}
                  className={`px-3.5 py-1.5 rounded-full font-label-sm text-label-sm ${type === t ? "bg-secondary-container text-on-secondary-fixed font-semibold" : "bg-surface-container-lowest/80 text-on-surface-variant hover:text-on-surface"}`}
                >
                  {TYPE_LABELS[t]} ({counts[t]})
                </button>
              ))}
              <Link
                href={`/project/insights/print?project=${projectId}`}
                target="_blank"
                className="ml-auto px-3.5 py-1.5 rounded-full bg-surface-container-lowest/80 text-on-surface font-label-sm text-label-sm flex items-center gap-1.5"
              >
                <Icon name="download" className="text-[14px]" /> Export to Report
              </Link>
            </div>

            {askOpen && (
              <div className="p-5 rounded-card bg-surface-container-lowest/90 shadow-card flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <span className="font-title-lg text-title-lg text-on-surface font-semibold flex items-center gap-2">
                    <Icon name="psychology" className="text-[20px] text-secondary" /> Ask a business question
                  </span>
                  <button type="button" aria-label="Close" onClick={() => setAskOpen(false)} className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:text-on-surface">
                    <Icon name="close" className="text-[18px]" />
                  </button>
                </div>
                <textarea
                  ref={askRef}
                  rows={2}
                  maxLength={300}
                  value={askText}
                  onChange={(e) => setAskText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void ask();
                    }
                  }}
                  placeholder="e.g. Which city has the highest revenue this year?"
                  className="w-full px-4 py-3 rounded-2xl bg-surface-container-low text-on-surface font-body-md text-body-md outline-none focus:ring-2 focus:ring-secondary-container resize-none"
                />
                <div className="flex items-center justify-between gap-3">
                  <span className="font-body-md text-xs text-on-surface-variant">The question is mapped to one of your measures and computed on your data; nothing is guessed.</span>
                  <button
                    type="button"
                    disabled={asking || !askText.trim()}
                    onClick={ask}
                    className="px-4 py-2 rounded-full bg-primary-container text-on-primary font-label-md text-label-md flex items-center gap-1.5 disabled:opacity-50 shrink-0"
                  >
                    <Icon name={asking ? "sync" : "send"} className={`text-[16px] ${asking ? "animate-spin" : ""}`} /> Ask
                  </button>
                </div>
              </div>
            )}

            {north && !type && !question && <NorthStarCard insight={north} busy={busy} onPin={() => togglePin(north)} />}
            {question && (
              <p className="px-1 font-body-md text-body-md text-on-surface-variant">
                Showing insights linked to: <span className="text-on-surface font-medium">{question.text}</span>
              </p>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {others.map((i) => (
                <InsightCard
                  key={i.id}
                  insight={i}
                  busy={busy}
                  onPin={() => togglePin(i)}
                  onRemove={i.type === "answer" ? () => run(() => deleteAsked(projectId, i.id)) : undefined}
                />
              ))}
            </div>
            {others.length === 0 && (question || type) && (
              <p className="px-1 font-body-md text-body-md text-on-surface-variant">No insights of this kind were found in the data.</p>
            )}
          </div>
        </div>
      )}

      <div className="sticky bottom-4 z-40 w-full">
        <div className="p-4 md:px-7 rounded-panel md:rounded-full bg-surface-container-lowest/90 backdrop-blur-xl shadow-[0_16px_40px_-8px_rgba(35,35,35,0.18)] flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-secondary-container" />
            <span className="font-label-md text-label-md text-on-surface">
              <strong className="font-semibold">Step 6 of 9</strong>
              {plan ? ` • ${insights.length} Insights synthesized • ${alerts} Anomaly flags • ${plan.pinned.length} pinned for the dashboard` : " • Computing…"}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 justify-end">
            <Link
              href={`/project/kpis?project=${projectId}`}
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md flex items-center gap-1.5"
            >
              <Icon name="arrow_back" className="text-[16px]" /> Back: KPIs &amp; DAX
            </Link>
            <Link
              href={`/project/insights/print?project=${projectId}`}
              target="_blank"
              className="px-4 py-2 rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-label-md text-label-md flex items-center gap-1.5"
            >
              <Icon name="file_download" className="text-[16px]" /> Export Insights Summary (.pdf)
            </Link>
            <PillButton href={`/project/design-method?project=${projectId}`} arrow>
              Next: Design Method
            </PillButton>
          </div>
        </div>
      </div>
    </div>
  );
}
