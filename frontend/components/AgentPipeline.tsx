"use client";

import { useEffect, useState } from "react";
import { AnalysisStep } from "@/lib/types";
import { CheckCircle2, Loader2, Clock } from "lucide-react";

// ------------------------------------------------------------------
// Agent definitions
// ------------------------------------------------------------------

interface AgentDef {
  id: string;
  name: string;
  role: string;
  emoji: string;
  model: string | null;
  storeOnly?: boolean; // Webb only appears for store analysis
}

const AGENTS: AgentDef[] = [
  {
    id: "scraping",
    name: "Webb",
    role: "Web Scraper",
    emoji: "🕸️",
    model: null,
    storeOnly: true,
  },
  {
    id: "categorization",
    name: "Iris",
    role: "Categorizer",
    emoji: "🔬",
    model: "Groq · Llama 3.3 70B",
  },
  {
    id: "clustering",
    name: "Echo",
    role: "Cluster Analyst",
    emoji: "🗂️",
    model: "sentence-transformers",
  },
  {
    id: "report",
    name: "Penn",
    role: "Reporter",
    emoji: "🖊️",
    model: "Gemini 2.5 Flash",
  },
  {
    id: "stella",
    name: "Nova",
    role: "Story Writer",
    emoji: "✨",
    model: "Gemini 2.5 Flash",
  },
];

// ------------------------------------------------------------------
// Status derivation
// ------------------------------------------------------------------

type AgentStatus = "hidden" | "waiting" | "active" | "done";

interface AgentStat {
  label: string;
}

function deriveStatuses(
  step: AnalysisStep,
  isScraping: boolean
): Record<string, AgentStatus> {
  const order = isScraping
    ? ["scraping", "categorization", "clustering", "report", "stella"]
    : ["categorization", "clustering", "report", "stella"];

  const activeId =
    step.type === "scraping"
      ? "scraping"
      : step.type === "categorization"
      ? "categorization"
      : step.type === "clustering"
      ? "clustering"
      : step.type === "report"
      ? "report"
      : step.type === "done"
      ? null
      : null;

  const statuses: Record<string, AgentStatus> = {};
  let foundActive = false;

  for (const id of order) {
    if (!isScraping && id === "scraping") {
      statuses[id] = "hidden";
      continue;
    }
    if (activeId === id) {
      statuses[id] = "active";
      foundActive = true;
    } else if (!foundActive) {
      statuses[id] = "done";
    } else {
      statuses[id] = "waiting";
    }
  }

  // All done when step is "done"
  if (step.type === "done") {
    for (const id of order) {
      statuses[id] = "done";
    }
  }

  return statuses;
}

// ------------------------------------------------------------------
// Progress bar for Iris (categorization)
// ------------------------------------------------------------------

function asymptoticProgress(elapsedMs: number, estimatedMs: number): number {
  const ratio = elapsedMs / estimatedMs;
  return Math.min(Math.tanh(ratio * 1.2) * 90, 90);
}

function IrisProgressBar({
  startedAt,
  estimatedMs,
}: {
  startedAt?: number;
  estimatedMs?: number;
}) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 250);
    return () => clearInterval(id);
  }, []);

  if (!startedAt) return null;

  const elapsed = Date.now() - startedAt;
  const elapsedSec = Math.floor(elapsed / 1000);
  const progress = estimatedMs ? asymptoticProgress(elapsed, estimatedMs) : 0;
  const estimatedSec = estimatedMs ? Math.round(estimatedMs / 1000) : null;

  return (
    <div className="mt-3 space-y-1">
      <div className="w-full h-1 bg-indigo-100 rounded-full overflow-hidden">
        {estimatedMs ? (
          <div
            className="h-full bg-indigo-500 rounded-full transition-all duration-300 ease-out"
            style={{ width: `${progress}%` }}
          />
        ) : (
          <div className="h-full bg-indigo-300 rounded-full animate-pulse w-1/3" />
        )}
      </div>
      <div className="flex justify-between text-xs text-indigo-400">
        <span>{elapsedSec}s</span>
        {estimatedSec && progress < 88 && <span>~{estimatedSec}s est.</span>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Single agent card
// ------------------------------------------------------------------

const FALLBACK_CHAINS: Record<string, string> = {
  categorization: "Groq · Llama 3.3 70B → OpenRouter · DeepSeek R1 → Gemini 2.5 Flash Lite",
  report: "Gemini 2.5 Flash Lite → Mistral Small → Groq · Llama 3.3 70B",
  stella: "Gemini 2.5 Flash Lite → Mistral Small → Groq · Llama 3.3 70B",
};

function AgentCard({
  agent,
  status,
  step,
  stat,
  usedFallback,
}: {
  agent: AgentDef;
  status: AgentStatus;
  step: AnalysisStep;
  stat?: AgentStat;
  usedFallback?: boolean;
}) {
  if (status === "hidden") return null;

  const isActive = status === "active";
  const isDone = status === "done";
  const isWaiting = status === "waiting";

  return (
    <div
      className={`
        flex-1 min-w-0 rounded-xl border p-4 transition-all duration-500
        ${isActive ? "border-indigo-300 bg-indigo-50 shadow-sm shadow-indigo-100" : ""}
        ${isDone ? "border-emerald-200 bg-emerald-50" : ""}
        ${isWaiting ? "border-gray-200 bg-white" : ""}
      `}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xl leading-none">{agent.emoji}</span>
          <div>
            <p className={`text-sm font-semibold leading-tight ${isActive ? "text-indigo-700" : isDone ? "text-emerald-700" : "text-gray-700"}`}>
              {agent.name}
            </p>
            <p className={`text-xs leading-tight ${isActive ? "text-indigo-500" : isDone ? "text-emerald-600" : "text-gray-500"}`}>
              {agent.role}
            </p>
          </div>
        </div>

        {/* Status icon */}
        <div className="mt-0.5 shrink-0">
          {isActive && <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />}
          {isDone && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
          {isWaiting && <Clock className="w-4 h-4 text-gray-300" />}
        </div>
      </div>

      {/* Model badge + fallback indicator */}
      <div className="mt-2 flex items-center gap-1.5 flex-wrap">
        <span className={`inline-block text-xs px-1.5 py-0.5 rounded font-mono ${
          isActive ? "bg-indigo-100 text-indigo-600" :
          isDone ? "bg-emerald-100 text-emerald-600" :
          "bg-gray-100 text-gray-500"
        }`}>
          {agent.model ?? "Python scraper"}
        </span>
        {isDone && usedFallback && FALLBACK_CHAINS[agent.id] && (
          <span
            title={`Fallback chain: ${FALLBACK_CHAINS[agent.id]}`}
            className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded font-medium bg-orange-100 text-orange-600 cursor-help"
          >
            ↩ fallback
          </span>
        )}
      </div>

      {/* Stat when done */}
      {isDone && stat && (
        <p className="mt-2 text-xs text-emerald-600 font-medium">{stat.label}</p>
      )}

      {/* Progress bar for Iris (categorization) or Hugo (report) when active */}
      {isActive && agent.id === "categorization" && step.type === "categorization" && (
        <IrisProgressBar startedAt={step.startedAt} estimatedMs={step.estimatedMs} />
      )}
      {isActive && agent.id === "report" && step.type === "report" && (
        <IrisProgressBar startedAt={step.startedAt} estimatedMs={step.estimatedMs} />
      )}
    </div>
  );
}

// ------------------------------------------------------------------
// Arrow connector
// ------------------------------------------------------------------

function Arrow({ active }: { active: boolean }) {
  return (
    <div className={`shrink-0 flex items-center justify-center px-1 transition-colors duration-500 ${active ? "text-indigo-300" : "text-gray-200"}`}>
      <svg width="20" height="12" viewBox="0 0 20 12" fill="none">
        <path d="M0 6h16M12 1l6 5-6 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// ------------------------------------------------------------------
// Main component
// ------------------------------------------------------------------

export default function AgentPipeline({
  step,
  scrapedCount,
  nFeedbacks,
  clusterCount,
  irisFallback,
  reportFallback,
}: {
  step: AnalysisStep;
  scrapedCount?: number;
  nFeedbacks?: number;
  clusterCount?: number;
  irisFallback?: boolean;
  reportFallback?: boolean;
}) {
  // isScraping is true as soon as scrapedCount is set (persisted by pipelineMetaRef in page.tsx),
  // OR while the scraping step is active — so Webb stays visible through the entire analysis.
  const isScraping = scrapedCount !== undefined || step.type === "scraping";

  const statuses = deriveStatuses(step, isScraping);

  const stats: Record<string, AgentStat> = {};
  if (scrapedCount !== undefined) {
    stats["scraping"] = { label: `${scrapedCount} reviews fetched` };
  }
  if (nFeedbacks !== undefined && statuses["categorization"] === "done") {
    stats["categorization"] = { label: `${nFeedbacks} feedbacks categorized` };
  }
  if (clusterCount !== undefined && statuses["clustering"] === "done") {
    stats["clustering"] = { label: `${clusterCount} clusters formed` };
  }

  const fallbacks: Record<string, boolean> = {
    categorization: irisFallback ?? false,
    report: reportFallback ?? false,
    stella: reportFallback ?? false,
  };

  const visibleAgents = AGENTS.filter((a) => statuses[a.id] !== "hidden");

  return (
    <div className="w-full">
      <p className="text-xs font-medium text-gray-400 mb-3 uppercase tracking-wide">
        Agent pipeline
      </p>
      <div className="flex items-stretch gap-0">
        {visibleAgents.map((agent, i) => (
          <div key={agent.id} className="flex items-center flex-1 min-w-0 gap-0">
            <AgentCard
              agent={agent}
              status={statuses[agent.id]}
              step={step}
              stat={stats[agent.id]}
              usedFallback={fallbacks[agent.id] ?? false}
            />
            {i < visibleAgents.length - 1 && (
              <Arrow active={statuses[agent.id] === "done"} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
