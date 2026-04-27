"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import InputPanel from "@/components/InputPanel";
import FeedbackTable from "@/components/FeedbackTable";
import { ExecutiveReport, FeedbackStats, FallbackBanner, IrisCorrections } from "@/components/ReportPanel";
import UserStoryCards from "@/components/UserStoryCards";
import AgentPipeline, { PipelineSource } from "@/components/AgentPipeline";
import { useAnalysis } from "@/lib/useAnalysis";
import { RotateCcw } from "lucide-react";
import AppFooter from "@/components/AppFooter";


export default function Home() {
  const { step, partialItems, appName, nonActionableItemsRef, actionableCountRef, allEstimatesRef, analyzeText, analyzeCsv, analyzeStore, reset, retry } = useAnalysis();
  const resultsRef = useRef<HTMLDivElement>(null);
  const pipelineMetaRef = useRef<{ nFeedbacks?: number; clusterCount?: number; siftedCount?: number }>({});
  const sourceRef = useRef<PipelineSource | undefined>(undefined);

  // Persist pipeline metadata across step transitions
  // Use the actionable count (from sifted event) once available, else fall back to raw nFeedbacks
  if (step.type === "categorization" || step.type === "clustering" || step.type === "report" || step.type === "stella" || step.type === "done") {
    const actionable = actionableCountRef.current;
    if (actionable !== null) {
      pipelineMetaRef.current.siftedCount = actionable;
      pipelineMetaRef.current.nFeedbacks = actionable;
    } else if (step.type === "categorization" && step.nFeedbacks !== undefined) {
      // Fallback: sifted event hasn't arrived yet (shouldn't happen, but safe)
      pipelineMetaRef.current.nFeedbacks = step.nFeedbacks;
      pipelineMetaRef.current.siftedCount = step.nFeedbacks;
    }
  }
  if (step.type === "clustering") {
    if (step.clusterCount !== undefined) pipelineMetaRef.current.clusterCount = step.clusterCount;
  }

  const isRunning = step.type !== "idle" && step.type !== "done" && step.type !== "error";
  const showResults = partialItems.length > 0 || step.type === "sift" || step.type === "categorization" || step.type === "done" || step.type === "error";
  const skeletonCount = step.type === "categorization" && partialItems.length === 0
    ? Math.min(step.nFeedbacks ?? 10, 10)
    : 0;

  useEffect(() => {
    if (showResults) {
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    }
  }, [showResults]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo.jpg" alt="trIAge logo" className="w-9 h-9 rounded-xl" />
            <div>
              <h1 className="text-lg font-semibold text-gray-900">trIAge</h1>
              <p className="text-xs text-gray-400">Product feedback triage for PMs, powered by AI agents</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/about"
              className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 border border-indigo-200 hover:border-indigo-400 hover:bg-indigo-50 px-3 py-1.5 rounded-lg transition-colors"
            >
              🔧 How it&apos;s built
            </Link>
            {step.type !== "idle" && (
              <button
                onClick={reset}
                className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                New analysis
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10 space-y-10">
        {/* Input section — hidden when running or done */}
        {step.type === "idle" && (
          <section className="space-y-6">
            <div className="space-y-2">
              <h2 className="text-2xl font-bold text-gray-900">Turn app reviews into Jira tickets</h2>
              <p className="text-sm text-gray-500">
                Pull feedbacks directly from the App Store/Google Play reviews or paste your app&apos;s feedbacks.
                Your AI agents will turn them into sprint-ready Jira tickets.
              </p>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <InputPanel
                onAnalyzeText={(feedbacks, name) => { sourceRef.current = "text"; analyzeText(feedbacks, name); }}
                onAnalyzeCsv={(file) => { sourceRef.current = "csv"; analyzeCsv(file); }}
                onAnalyzeStore={(app, store, count) => { sourceRef.current = store === "googleplay" ? "googleplay" : "appstore"; analyzeStore(app, store, count); }}
disabled={isRunning}
              />
            </div>
          </section>
        )}

        {/* Error */}
        {step.type === "error" && (() => {
          const msg = step.message || "";
          const isQuotaExhausted = /quota exhausted|429|RESOURCE_EXHAUSTED/i.test(msg);
          const isTransient = /503|UNAVAILABLE|high demand|rate.?limit|try again/i.test(msg);
          const friendly = isQuotaExhausted
            ? "Daily free-tier quota exhausted across Cerebras, Gemini and fallback providers. Retry in a few minutes or tomorrow (Gemini resets at midnight Pacific, Cerebras resets daily)."
            : isTransient
            ? "The AI model is temporarily overloaded. This usually clears up within a minute."
            : "Something went wrong during the analysis.";
          return (
            <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 text-sm text-red-700">
              <p className="font-medium">Analysis failed</p>
              <p className="text-xs mt-1 opacity-80">{friendly}</p>
              <div className="flex items-center gap-3 mt-3">
                <button
                  onClick={() => retry()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-semibold hover:bg-red-700 transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Retry
                </button>
                <details className="text-xs opacity-70">
                  <summary className="cursor-pointer hover:opacity-100">Technical details</summary>
                  <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-[10px]">{msg}</pre>
                </details>
              </div>
            </div>
          );
        })()}

        <div ref={resultsRef} className="space-y-10">
          {/* App name badge */}
          {appName && (isRunning || step.type === "done") && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Analyzing</span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700">
                {appName}
              </span>
            </div>
          )}

          {/* 1 — Agent pipeline */}
          {(isRunning || step.type === "done") && (
            <section className="py-4">
              <AgentPipeline
                step={step}
                nFeedbacks={pipelineMetaRef.current.nFeedbacks}
                clusterCount={pipelineMetaRef.current.clusterCount}
                siftedCount={pipelineMetaRef.current.siftedCount}
                irisFallback={
                  step.type === "done" ? step.result.used_fallback :
                  step.type === "categorization" ? step.usedFallback :
                  undefined
                }
                irisFallbackProvider={step.type === "done" ? step.result.iris_fallback_provider : undefined}
                reportFallback={step.type === "done" ? step.result.report_fallback : undefined}
                reportFallbackProvider={step.type === "done" ? step.result.report_fallback_provider : undefined}
                cardsFallbackProvider={step.type === "done" ? step.result.cards_fallback_provider : undefined}
                source={sourceRef.current}
                estimates={allEstimatesRef.current}
              />
            </section>
          )}

          {step.type === "done" && (
            <>
              {/* 2 — Executive Report */}
              {step.result.report && (
                <section>
                  <ExecutiveReport report={step.result.report} />
                </section>
              )}

              {/* Sprint cards */}
              {step.result.user_story_cards.length > 0 && (
                <section>
                  <UserStoryCards cards={step.result.user_story_cards} />
                </section>
              )}

              {/* 3 — Summary stats */}
              <section>
                <FeedbackStats items={step.result.items} />
                <FallbackBanner
                  used_fallback={step.result.used_fallback}
                  report_fallback={step.result.report_fallback}
                />
              </section>
            </>
          )}

          {/* 4 — Actionable feedbacks */}
          {showResults && (partialItems.length > 0 || skeletonCount > 0 || (step.type === "done" && (step.result.non_actionable_items?.length ?? 0) > 0)) && (
            <section className="space-y-2">
              <h2 className="text-sm font-medium text-gray-500">
                Actionable feedbacks
                {isRunning && step.type === "report" && (
                  <span className="ml-2 text-xs text-indigo-500 animate-pulse">Generating report…</span>
                )}
              </h2>
              <FeedbackTable
                items={partialItems}
                skeletonCount={skeletonCount}
                nonActionableItems={step.type === "done" ? (step.result.non_actionable_items ?? []) : nonActionableItemsRef.current}
              />
            </section>
          )}

          {/* 5 — Iris self-corrections */}
          {step.type === "done" && (
            <section>
              <IrisCorrections result={step.result} />
            </section>
          )}
        </div>
      </main>

      <AppFooter />
    </div>
  );
}
