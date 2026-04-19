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

export default function Home() {
  const { step, partialItems, appName, nonActionableItemsRef, analyzeText, analyzeCsv, analyzeStore, reset, retry } = useAnalysis();
  const resultsRef = useRef<HTMLDivElement>(null);
  const pipelineMetaRef = useRef<{ nFeedbacks?: number; clusterCount?: number; siftedCount?: number }>({});
  const sourceRef = useRef<PipelineSource | undefined>(undefined);

  // Persist pipeline metadata across step transitions
  if (step.type === "categorization") {
    if (step.nFeedbacks !== undefined) {
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
              <h2 className="text-2xl font-bold text-gray-900">Triage your app reviews in seconds</h2>
              <p className="text-sm text-gray-500">
                Pull feedbacks directly from the App Store or Google Play reviews, upload a CSV, paste feedback, or use our demo feedback samples.
                Your AI agents will categorize, prioritize, and turn them into sprint-ready cards.
              </p>
            </div>

            {/* Agent pipeline preview */}
            <div className="flex items-center gap-0">
              {/* Source pill — static, shows Google Play as example */}
              <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 bg-white border border-gray-200 shadow-sm" title="Google Play / App Store / CSV">
                <svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">
                  <path d="M1.22 0c-.338.196-.22.618-.22 1.03v21.94c0 .414-.118.834.22 1.03l.08.06 12.28-12.26v-.3L1.3-.06l-.08.06z" fill="#4285F4"/>
                  <path d="M17.68 16.49l-4.09-4.1v-.3l4.09-4.09.09.05 4.84 2.75c1.38.78 1.38 2.06 0 2.84l-4.84 2.75-.09.05z" fill="#FBBC04"/>
                  <path d="M17.77 16.44L13.5 12 1.22 24.26c.456.484 1.207.544 1.74.14l14.81-7.96" fill="#EA4335"/>
                  <path d="M17.77 7.56L2.96.74C2.427.336 1.676.396 1.22.88L13.5 12l4.27-4.44z" fill="#34A853"/>
                </svg>
              </div>
              <div className="w-3 h-0.5 bg-gray-200 shrink-0" />

              <div className="flex items-stretch gap-2 flex-1 min-w-0">
                {[
                  { emoji: "🎯", name: "Sift", role: "Pre-filter", model: "Gemini 2.5 Flash Lite", desc: "Filters non-actionable feedback" },
                  { emoji: "🔬", name: "Iris", role: "Categorizer", model: "Groq · Llama 3.3 70B", desc: "Tags & prioritizes every feedback" },
                  { emoji: "🗂️", name: "Echo", role: "Cluster Analyst", model: "Gemini 2.5 Flash Lite", desc: "Groups feedbacks by semantic similarity" },
                  { emoji: "🖊️", name: "Penn", role: "Reporter", model: "Gemini 2.5 Flash", desc: "Writes the executive summary" },
                  { emoji: "✨", name: "Nova", role: "Backlog Builder", model: "Gemini 2.5 Flash", desc: "Generates sprint cards with RICE scoring" },
                ].map((a, i, arr) => (
                  <div key={a.name} className="flex items-center flex-1 min-w-0 gap-2">
                    <div className="flex-1 min-w-0 rounded-xl border border-gray-200 bg-white p-3 text-center">
                      <div className="text-xl mb-1">{a.emoji}</div>
                      <div className="text-xs font-semibold text-gray-800">{a.name}</div>
                      <div className="text-[10px] text-indigo-500 font-medium mb-0.5">{a.role}</div>
                      <div className="text-[10px] font-mono text-gray-400 mb-1">{a.model}</div>
                      <div className="text-[10px] text-gray-400 leading-snug">{a.desc}</div>
                    </div>
                    {i < arr.length - 1 && (
                      <span className="shrink-0 text-gray-300 text-sm">→</span>
                    )}
                  </div>
                ))}
              </div>

              <div className="w-3 h-0.5 bg-gray-200 shrink-0" />
              {/* Jira output pill */}
              <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 bg-[#0052CC] shadow-sm" title="Jira">
                <svg viewBox="0 0 32 32" width="16" height="16" xmlns="http://www.w3.org/2000/svg">
                  <path d="M15.88 0C11.37 0 8.34 3.12 8.34 7.74v1.04H3.07C3.07 13.44 6 16.6 10.38 16.6h1.32v8.44C11.7 29.08 14.84 32 19.44 32V10.42h5.29C24.73 5.66 21.7 0 15.88 0z" fill="white"/>
                  <path d="M11.7 8.78H8.34c0 4.66 2.93 7.82 7.31 7.82h1.32V9.56l-.14-.78H11.7z" fill="rgba(255,255,255,0.55)"/>
                  <path d="M16.88 17.04h-1.44c0 4.66 3.13 7.96 7.5 7.96v-7.18l-.13-.78h-5.93z" fill="rgba(255,255,255,0.55)"/>
                </svg>
              </div>
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
            ? "Daily free-tier quota exhausted on both Groq and Gemini. Retry in a few minutes (Groq resets quickly) or tomorrow (Gemini resets at midnight Pacific)."
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
                reportFallback={step.type === "done" ? step.result.report_fallback : undefined}
                source={sourceRef.current}
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

      <footer className="border-t border-gray-200 mt-6 py-4">
        <div className="max-w-4xl mx-auto px-6 flex items-center justify-center gap-3 text-xs text-gray-400">
          <span>Made by <span className="font-medium text-gray-500">Samuel PILOT</span></span>
          <span>·</span>
          <a href="https://linktr.ee/samuelpilot" target="_blank" rel="noopener noreferrer" className="hover:text-indigo-500 transition-colors">🌳 LinkTree</a>
          <span>·</span>
          <a href="mailto:samuelpilotbasse@gmail.com" className="hover:text-indigo-500 transition-colors">✉️ Contact</a>
        </div>
      </footer>
    </div>
  );
}
