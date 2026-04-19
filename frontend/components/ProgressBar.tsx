"use client";

import { useEffect, useState } from "react";
import { AnalysisStep } from "@/lib/types";
import { Loader2 } from "lucide-react";

const STEPS = [
  { key: "scraping", label: "Fetching reviews" },
  { key: "categorization", label: "Categorizing" },
  { key: "report", label: "Generating report" },
  { key: "done", label: "Done" },
];

// Asymptotic progress: grows quickly toward ~85%, then slows, never reaches 100%
// until the real event arrives.
function asymptoticProgress(elapsedMs: number, estimatedMs: number): number {
  if (estimatedMs <= 0) return 0;
  const ratio = elapsedMs / estimatedMs;
  // tanh-based curve: fast start, decelerates, caps at ~90%
  const raw = Math.tanh(ratio * 1.2) * 90;
  return Math.min(raw, 90);
}

function useElapsedProgress(
  startedAt: number | undefined,
  estimatedMs: number | undefined
): { progress: number; elapsedSec: number } {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!startedAt || !estimatedMs) return;
    const id = setInterval(() => setTick((t) => t + 1), 250);
    return () => clearInterval(id);
  }, [startedAt, estimatedMs]);

  if (!startedAt || !estimatedMs) return { progress: 0, elapsedSec: 0 };
  const elapsed = Date.now() - startedAt;
  return {
    progress: asymptoticProgress(elapsed, estimatedMs),
    elapsedSec: Math.floor(elapsed / 1000),
  };
}

function CategorizationProgress({
  estimatedMs,
  startedAt,
}: {
  estimatedMs?: number;
  startedAt?: number;
}) {
  const { progress, elapsedSec } = useElapsedProgress(startedAt, estimatedMs);
  const estimatedSec = estimatedMs ? Math.round(estimatedMs / 1000) : null;

  return (
    <div className="w-full space-y-1.5">
      <div className="flex justify-between text-xs text-gray-500">
        <span>Analyzing feedbacks…</span>
        <span>
          {elapsedSec}s
          {estimatedSec && progress < 88 ? ` / ~${estimatedSec}s` : ""}
        </span>
      </div>
      <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-500 rounded-full transition-all duration-300 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
      {!estimatedMs && (
        <p className="text-xs text-gray-400 italic">First run — no timing reference yet</p>
      )}
    </div>
  );
}

export default function ProgressBar({ step }: { step: AnalysisStep }) {
  if (step.type === "idle") return null;
  if (step.type === "error") return null;

  // Nova (stella) shares the "report" top-level phase for this coarse indicator
  const effectiveType = step.type === "stella" ? "report" : step.type;
  const currentIndex = STEPS.findIndex((s) => s.key === effectiveType);
  const showScraping = step.type === "scraping";

  return (
    <div className="w-full max-w-2xl mx-auto space-y-5">
      {/* Step indicators */}
      <div className="flex items-center gap-2">
        {STEPS.filter((s) => s.key !== "scraping" || showScraping).map((s) => {
          const idx = STEPS.indexOf(s);
          const done = currentIndex > idx;
          const active = currentIndex === idx;
          return (
            <div key={s.key} className="flex items-center gap-2 flex-1 last:flex-none">
              <div className="flex items-center gap-1.5">
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-xs transition-colors ${
                    done
                      ? "bg-indigo-600 text-white"
                      : active
                      ? "bg-indigo-100 border-2 border-indigo-600"
                      : "bg-gray-100"
                  }`}
                >
                  {done ? "✓" : active ? <Loader2 className="w-3 h-3 text-indigo-600 animate-spin" /> : ""}
                </div>
                <span
                  className={`text-xs font-medium ${
                    active ? "text-indigo-600" : done ? "text-gray-700" : "text-gray-400"
                  }`}
                >
                  {s.label}
                </span>
              </div>
              {idx < STEPS.length - 2 && (
                <div className={`flex-1 h-px mx-1 ${done ? "bg-indigo-300" : "bg-gray-200"}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Categorization progress bar */}
      {step.type === "categorization" && (
        <CategorizationProgress
          estimatedMs={step.estimatedMs}
          startedAt={step.startedAt}
        />
      )}
    </div>
  );
}
