"use client";

import { useEffect, useState } from "react";
import { AnalysisStep } from "@/lib/types";
import { CheckCircle2, Loader2, Clock, ClipboardList, FileSpreadsheet } from "lucide-react";

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
    id: "sift",
    name: "Sift",
    role: "Pre-filter",
    emoji: "🎯",
    model: "Cerebras · gpt-oss-120b",
  },
  {
    id: "categorization",
    name: "Iris",
    role: "Categorizer",
    emoji: "🔬",
    model: "Gemini 3.1 Flash Lite",
  },
  {
    id: "clustering",
    name: "Echo",
    role: "Cluster Analyst",
    emoji: "🗂️",
    model: "Cerebras · gpt-oss-120b",
  },
  {
    id: "report",
    name: "Penn",
    role: "Reporter",
    emoji: "🖊️",
    model: "Cerebras · Qwen 3 235B",
  },
  {
    id: "stella",
    name: "Nova",
    role: "Story Writer",
    emoji: "🃏",
    model: "Cerebras · Qwen 3 235B",
  },
];

// ------------------------------------------------------------------
// Status derivation
// ------------------------------------------------------------------

type AgentStatus = "hidden" | "waiting" | "active" | "done";

interface AgentStat {
  label: string;
}

function deriveStatuses(step: AnalysisStep): Record<string, AgentStatus> {
  const order = ["sift", "categorization", "clustering", "report", "stella"];

  const activeId =
    step.type === "sift" ? "sift"
    : step.type === "categorization" ? "categorization"
    : step.type === "clustering" ? "clustering"
    : step.type === "report" ? "report"
    : step.type === "stella" ? "stella"
    : null;

  const statuses: Record<string, AgentStatus> = {};
  let foundActive = false;

  for (const id of order) {
    if (activeId === id) {
      statuses[id] = "active";
      foundActive = true;
    } else if (!foundActive) {
      statuses[id] = "done";
    } else {
      statuses[id] = "waiting";
    }
  }

  if (step.type === "done") {
    for (const id of order) statuses[id] = "done";
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
  sift: "Cerebras · gpt-oss-120b → Gemini 3.1 Flash Lite → Mistral Small → OpenRouter · auto → Groq · Llama 3.3 70B",
  categorization: "Gemini 3.1 Flash Lite → Groq · Llama 3.3 70B → OpenRouter · auto",
  clustering: "Cerebras · gpt-oss-120b → Gemini 3.1 Flash Lite → Mistral Small → OpenRouter · auto → Groq · Llama 3.3 70B",
  report: "Cerebras · Qwen 3 235B → Gemini 3.1 Flash Lite → Mistral Small → OpenRouter · auto → Groq · Llama 3.3 70B",
  stella: "Cerebras · Qwen 3 235B → Gemini 3.1 Flash Lite → Mistral Small → OpenRouter · auto → Groq · Llama 3.3 70B",
};

function AgentCard({
  agent,
  status,
  step,
  stat,
  usedFallback,
  estimatedMs,
}: {
  agent: AgentDef;
  status: AgentStatus;
  step: AnalysisStep;
  stat?: AgentStat;
  usedFallback?: boolean;
  estimatedMs?: number;
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
        {usedFallback && FALLBACK_CHAINS[agent.id] && (
          <span
            title={`Fallback chain: ${FALLBACK_CHAINS[agent.id]}`}
            className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded font-medium bg-orange-100 text-orange-600 cursor-help"
          >
            ↩ fallback
          </span>
        )}
      </div>

      {/* Estimated duration when waiting */}
      {isWaiting && estimatedMs && (
        <p className="mt-2 text-xs text-gray-400">~{Math.round(estimatedMs / 1000)}s</p>
      )}

      {/* Stat when done */}
      {isDone && stat && (
        <p className="mt-2 text-xs text-emerald-600 font-medium">{stat.label}</p>
      )}

      {/* Progress bars */}
      {isActive && agent.id === "sift" && step.type === "sift" && (
        <IrisProgressBar startedAt={step.startedAt} estimatedMs={step.estimatedMs} />
      )}
      {isActive && agent.id === "categorization" && step.type === "categorization" && (
        <IrisProgressBar startedAt={step.startedAt} estimatedMs={step.estimatedMs} />
      )}
      {isActive && agent.id === "clustering" && step.type === "clustering" && (
        <IrisProgressBar startedAt={step.startedAt} estimatedMs={step.estimatedMs} />
      )}
      {isActive && agent.id === "report" && step.type === "report" && (
        <IrisProgressBar startedAt={step.startedAt} estimatedMs={step.estimatedMs} />
      )}
      {isActive && agent.id === "stella" && step.type === "stella" && (
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
// Source / output icon pills
// ------------------------------------------------------------------

export type PipelineSource = "googleplay" | "appstore" | "csv" | "text";

function GooglePlayIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">
      <path d="M1.22 0c-.338.196-.22.618-.22 1.03v21.94c0 .414-.118.834.22 1.03l.08.06 12.28-12.26v-.3L1.3-.06l-.08.06z" fill="#4285F4"/>
      <path d="M17.68 16.49l-4.09-4.1v-.3l4.09-4.09.09.05 4.84 2.75c1.38.78 1.38 2.06 0 2.84l-4.84 2.75-.09.05z" fill="#FBBC04"/>
      <path d="M17.77 16.44L13.5 12 1.22 24.26c.456.484 1.207.544 1.74.14l14.81-7.96" fill="#EA4335"/>
      <path d="M17.77 7.56L2.96.74C2.427.336 1.676.396 1.22.88L13.5 12l4.27-4.44z" fill="#34A853"/>
    </svg>
  );
}

function AppStoreIcon() {
  // Apple logo (universally recognised as App Store) on blue background
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">
      <rect width="24" height="24" rx="5.5" fill="#0D96F6"/>
      <path d="M15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701z" fill="white" transform="translate(0,2)"/>
      <path d="M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.029 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09z" fill="white" transform="translate(0,2) scale(0.83) translate(1.5,0)"/>
    </svg>
  );
}

function CsvIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#6b7280" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
    </svg>
  );
}

function JiraIcon() {
  // Official Jira logo (Simple Icons / Atlassian brand)
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" xmlns="http://www.w3.org/2000/svg" fill="white">
      <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.004-1.005zm5.723-5.756H5.757a5.215 5.215 0 0 0 5.214 5.214h2.132v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.024-1.001zM23.013 0H11.476a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.49V1.005A1.001 1.001 0 0 0 23.013 0z"/>
    </svg>
  );
}

function SourcePill({ source }: { source: PipelineSource }) {
  const base = "w-9 h-9 rounded-full flex items-center justify-center shrink-0 border shadow-sm";
  if (source === "googleplay") return <div className={`${base} bg-white border-gray-200`} title="Google Play"><GooglePlayIcon /></div>;
  if (source === "appstore")   return <div className={`${base} bg-white border-gray-200`} title="App Store"><AppStoreIcon /></div>;
  if (source === "csv")        return <div className={`${base} bg-white border-gray-200`} title="CSV upload"><FileSpreadsheet className="w-5 h-5 text-gray-500" /></div>;
  return <div className={`${base} bg-white border-gray-200`} title="Paste / Demo"><ClipboardList className="w-5 h-5 text-gray-500" /></div>;
}

function JiraPill() {
  return (
    <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 bg-[#0052CC] shadow-sm" title="Jira">
      <JiraIcon />
    </div>
  );
}

function PillConnector() {
  return <div className="w-4 h-0.5 bg-gray-200 shrink-0" />;
}

// ------------------------------------------------------------------
// Main component
// ------------------------------------------------------------------

export default function AgentPipeline({
  step,
  nFeedbacks,
  clusterCount,
  siftedCount,
  irisFallback,
  reportFallback,
  siftFallback,
  source,
  estimates,
}: {
  step: AnalysisStep;
  nFeedbacks?: number;
  clusterCount?: number;
  siftedCount?: number;
  irisFallback?: boolean;
  reportFallback?: boolean;
  siftFallback?: boolean;
  source?: PipelineSource;
  estimates?: Partial<Record<string, number>>;
}) {
  const statuses = deriveStatuses(step);

  const stats: Record<string, AgentStat> = {};
  if (siftedCount !== undefined && statuses["sift"] === "done") {
    stats["sift"] = { label: `${siftedCount} actionable` };
  }
  if (nFeedbacks !== undefined && statuses["categorization"] === "done") {
    stats["categorization"] = { label: `${nFeedbacks} feedbacks categorized` };
  }
  if (clusterCount !== undefined && statuses["clustering"] === "done") {
    stats["clustering"] = { label: `${clusterCount} clusters formed` };
  }

  const fallbacks: Record<string, boolean> = {
    sift: siftFallback ?? false,
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
      <div className="flex items-center gap-0">
        {/* Source pill */}
        {source && (
          <>
            <SourcePill source={source} />
            <PillConnector />
          </>
        )}

        {/* Agent cards */}
        <div className="flex items-stretch gap-0 flex-1 min-w-0">
          {visibleAgents.map((agent, i) => (
            <div key={agent.id} className="flex items-center flex-1 min-w-0 gap-0">
              <AgentCard
                agent={agent}
                status={statuses[agent.id]}
                step={step}
                stat={stats[agent.id]}
                usedFallback={fallbacks[agent.id] ?? false}
                estimatedMs={estimates?.[agent.id]}
              />
              {i < visibleAgents.length - 1 && (
                <Arrow active={statuses[agent.id] === "done"} />
              )}
            </div>
          ))}
        </div>

        {/* Jira output pill */}
        {source && (
          <>
            <PillConnector />
            <JiraPill />
          </>
        )}
      </div>
    </div>
  );
}
