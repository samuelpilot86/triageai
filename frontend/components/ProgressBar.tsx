"use client";

import { AnalysisStep } from "@/lib/types";
import { Loader2 } from "lucide-react";

const STEPS = [
  { key: "scraping", label: "Fetching reviews" },
  { key: "categorization", label: "Categorizing" },
  { key: "report", label: "Generating report" },
  { key: "done", label: "Done" },
];

export default function ProgressBar({ step }: { step: AnalysisStep }) {
  if (step.type === "idle") return null;
  if (step.type === "error") return null;

  const currentIndex = STEPS.findIndex((s) => s.key === step.type);

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="flex items-center gap-2">
        {STEPS.filter((s) => s.key !== "scraping" || step.type === "scraping").map((s, i) => {
          const idx = STEPS.indexOf(s);
          const done = currentIndex > idx;
          const active = currentIndex === idx;
          return (
            <div key={s.key} className="flex items-center gap-2 flex-1 last:flex-none">
              <div className="flex items-center gap-1.5">
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-xs transition-colors ${
                    done ? "bg-indigo-600 text-white" : active ? "bg-indigo-100 border-2 border-indigo-600" : "bg-gray-100"
                  }`}
                >
                  {done ? "✓" : active ? <Loader2 className="w-3 h-3 text-indigo-600 animate-spin" /> : ""}
                </div>
                <span className={`text-xs font-medium ${active ? "text-indigo-600" : done ? "text-gray-700" : "text-gray-400"}`}>
                  {s.label}
                </span>
              </div>
              {i < STEPS.length - 2 && <div className={`flex-1 h-px mx-1 ${done ? "bg-indigo-300" : "bg-gray-200"}`} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
