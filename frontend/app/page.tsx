"use client";

import { useEffect, useRef } from "react";
import InputPanel from "@/components/InputPanel";
import FeedbackTable from "@/components/FeedbackTable";
import ReportPanel from "@/components/ReportPanel";
import UserStoryCards from "@/components/UserStoryCards";
import ProgressBar from "@/components/ProgressBar";
import { useAnalysis } from "@/lib/useAnalysis";
import { RotateCcw } from "lucide-react";

export default function Home() {
  const { step, partialItems, analyzeText, analyzeCsv, analyzeStore, reset } = useAnalysis();
  const resultsRef = useRef<HTMLDivElement>(null);

  const isRunning = step.type !== "idle" && step.type !== "done" && step.type !== "error";
  const showResults = partialItems.length > 0 || step.type === "done" || step.type === "error";

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
          <div>
            <h1 className="text-lg font-semibold text-gray-900">trIAge</h1>
            <p className="text-xs text-gray-400">Product feedback triage, powered by AI</p>
          </div>
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
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10 space-y-10">
        {/* Input section — hidden when running or done */}
        {step.type === "idle" && (
          <section className="space-y-2">
            <h2 className="text-sm font-medium text-gray-500">Input</h2>
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <InputPanel
                onAnalyzeText={analyzeText}
                onAnalyzeCsv={analyzeCsv}
                onAnalyzeStore={analyzeStore}
                disabled={isRunning}
              />
            </div>
          </section>
        )}

        {/* Progress */}
        {isRunning && (
          <section className="flex flex-col items-center gap-6 py-8">
            <ProgressBar step={step} />
          </section>
        )}

        {/* Error */}
        {step.type === "error" && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 text-sm text-red-700">
            <p className="font-medium">Analysis failed</p>
            <p className="text-xs mt-1 opacity-80">{step.message}</p>
          </div>
        )}

        {/* Results */}
        {showResults && (
          <div ref={resultsRef} className="space-y-8">
            {partialItems.length > 0 && (
              <section className="space-y-2">
                <h2 className="text-sm font-medium text-gray-500">
                  Detailed results
                  {isRunning && step.type === "report" && (
                    <span className="ml-2 text-xs text-indigo-500 animate-pulse">Generating report…</span>
                  )}
                </h2>
                <FeedbackTable items={partialItems} />
              </section>
            )}

            {step.type === "done" && (
              <section className="space-y-8">
                <ReportPanel result={step.result} />
                {step.result.user_story_cards.length > 0 && (
                  <UserStoryCards cards={step.result.user_story_cards} />
                )}
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
