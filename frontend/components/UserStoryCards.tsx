"use client";

import { useState } from "react";
import { UserStoryCard, ActionType, RiceScore, SprintFeedback } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

// ------------------------------------------------------------------
// Jira button with confirmation modal
// ------------------------------------------------------------------

function JiraButton({ card }: { card: UserStoryCard }) {
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ key: string; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function sendToJira() {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/jira/create-issue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(card),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setResult(data);
      setShowModal(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  if (result) {
    return (
      <a
        href={result.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors"
      >
        <img src="https://www.atlassian.com/favicon.ico" className="w-3 h-3" alt="" />
        {result.key} ↗
      </a>
    );
  }

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600 transition-colors"
      >
        <img src="https://www.atlassian.com/favicon.ico" className="w-3 h-3" alt="" />
        Create Jira ticket
      </button>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-4">
            <h3 className="text-sm font-semibold text-gray-900">Create Jira ticket</h3>
            <div className="space-y-2 text-xs text-gray-600">
              <div><span className="font-medium text-gray-500">Title</span><p className="mt-0.5 text-gray-800 font-medium">{card.action}</p></div>
              <div><span className="font-medium text-gray-500">Type</span><p className="mt-0.5">{card.action_type}</p></div>
              {card.rice && <div><span className="font-medium text-gray-500">RICE score</span><p className="mt-0.5">{card.rice.score}</p></div>}
              {card.user_story && <div><span className="font-medium text-gray-500">User story</span><p className="mt-0.5">{card.user_story}</p></div>}
              {card.next_step && <div><span className="font-medium text-gray-500">Next step</span><p className="mt-0.5">{card.next_step}</p></div>}
            </div>
            {error && <p className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button onClick={() => { setShowModal(false); setError(null); }} className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700">Cancel</button>
              <button
                onClick={sendToJira}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:opacity-50 hover:bg-blue-700 transition-colors"
              >
                {loading ? "Sending…" : "Send to Jira →"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------
// Type metadata
// ------------------------------------------------------------------

const TYPE_META: Record<ActionType, { emoji: string; label: string; color: string; border: string; badge: string }> = {
  bug:         { emoji: "🐛", label: "Bug",         color: "text-red-700",    border: "border-l-red-400",    badge: "bg-red-100 text-red-700" },
  performance: { emoji: "⚡", label: "Performance", color: "text-orange-700", border: "border-l-orange-400", badge: "bg-orange-100 text-orange-700" },
  feature:     { emoji: "✨", label: "Feature",     color: "text-indigo-700", border: "border-l-indigo-400", badge: "bg-indigo-100 text-indigo-700" },
  ux:          { emoji: "🎨", label: "UX",          color: "text-violet-700", border: "border-l-violet-400", badge: "bg-violet-100 text-violet-700" },
  pricing:     { emoji: "💰", label: "Pricing",     color: "text-emerald-700",border: "border-l-emerald-400",badge: "bg-emerald-100 text-emerald-700" },
  ai_quality:  { emoji: "🤖", label: "AI Quality",  color: "text-blue-700",   border: "border-l-blue-400",   badge: "bg-blue-100 text-blue-700" },
  other:       { emoji: "📌", label: "Other",       color: "text-gray-700",   border: "border-l-gray-400",   badge: "bg-gray-100 text-gray-600" },
};

// ------------------------------------------------------------------
// RICE bar
// ------------------------------------------------------------------

const IMPACT_LABEL: Record<number, string> = { 1: "Low", 2: "Medium", 3: "High" };

function RiceBar({ rice }: { rice: RiceScore }) {
  const confidencePct = Math.round(rice.confidence * 100);
  return (
    <div className="grid grid-cols-4 gap-2 text-center">
      {/* Reach */}
      <div className="bg-gray-50 rounded-lg px-2 py-2">
        <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Reach</p>
        <p className="text-lg font-bold text-gray-800 leading-tight">{rice.reach}</p>
        <p className="text-xs text-gray-400">feedbacks</p>
      </div>
      {/* Impact */}
      <div className="bg-gray-50 rounded-lg px-2 py-2">
        <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Impact</p>
        <p className="text-lg font-bold text-gray-800 leading-tight">{rice.impact}<span className="text-xs text-gray-400 font-normal">/3</span></p>
        <p className="text-xs text-gray-400">{IMPACT_LABEL[rice.impact]}</p>
      </div>
      {/* Confidence */}
      <div className="bg-gray-50 rounded-lg px-2 py-2">
        <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Confidence</p>
        <p className="text-lg font-bold text-gray-800 leading-tight">{confidencePct}<span className="text-xs text-gray-400 font-normal">%</span></p>
        <div className="mt-0.5 w-full h-1 bg-gray-200 rounded-full overflow-hidden">
          <div className="h-full bg-indigo-400 rounded-full" style={{ width: `${confidencePct}%` }} />
        </div>
      </div>
      {/* Effort */}
      <div className="bg-gray-50 rounded-lg px-2 py-2">
        <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Effort</p>
        <p className="text-lg font-bold text-gray-800 leading-tight">{rice.effort_label}</p>
        <p className="text-xs text-gray-400">
          {rice.effort_label === "XS" ? "hours" :
           rice.effort_label === "S"  ? "days" :
           rice.effort_label === "M"  ? "1–2 sprints" :
           rice.effort_label === "L"  ? "3–4 sprints" : "quarter+"}
        </p>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Content section — adaptive by type
// ------------------------------------------------------------------

function CardContent({ card }: { card: UserStoryCard }) {
  const isBugPerf = card.action_type === "bug" || card.action_type === "performance";
  const isFeature = card.action_type === "feature";

  if (isBugPerf) {
    return (
      <div className="space-y-3">
        {card.what_breaks && (
          <Row label="What breaks" value={card.what_breaks} />
        )}
        {card.done_when && (
          <Row label="Done when" value={card.done_when} icon="✓" iconColor="text-emerald-500" />
        )}
        {card.next_step && (
          <Row label="Next step" value={card.next_step} icon="→" iconColor="text-indigo-400" />
        )}
      </div>
    );
  }

  if (isFeature) {
    return (
      <div className="space-y-3">
        {card.user_story && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">User story</p>
            <p className="text-sm font-medium text-gray-800">{card.user_story}</p>
          </div>
        )}
        {card.acceptance_criteria && card.acceptance_criteria.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Acceptance criteria</p>
            <ul className="space-y-1">
              {card.acceptance_criteria.map((ac, i) => (
                <li key={i} className="flex gap-2 text-xs text-gray-600">
                  <span className="text-emerald-500 font-bold shrink-0 select-none">□</span>
                  <span>{ac}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {card.next_step && (
          <Row label="Next step" value={card.next_step} icon="→" iconColor="text-indigo-400" />
        )}
      </div>
    );
  }

  // ux / pricing / other
  return (
    <div className="space-y-3">
      {card.problem && (
        <Row label="Problem" value={card.problem} />
      )}
      {card.success_metric && (
        <Row label="Success metric" value={card.success_metric} icon="✓" iconColor="text-emerald-500" />
      )}
      {card.next_step && (
        <Row label="Next step" value={card.next_step} icon="→" iconColor="text-indigo-400" />
      )}
    </div>
  );
}

function Row({ label, value, icon, iconColor }: { label: string; value: string; icon?: string; iconColor?: string }) {
  return (
    <div className="flex gap-2">
      {icon && <span className={`shrink-0 text-sm font-bold select-none ${iconColor}`}>{icon}</span>}
      <div>
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{label} </span>
        <span className="text-sm text-gray-700">{value}</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Main component
// ------------------------------------------------------------------

export default function UserStoryCards({ cards }: { cards: UserStoryCard[] }) {
  if (!cards.length) return null;

  // Sorted by RICE score desc (backend already sorts, but ensure it here too)
  const sorted = [...cards].sort((a, b) => (b.rice?.score ?? 0) - (a.rice?.score ?? 0));

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-gray-900">Sprint cards · sorted by RICE score</h2>
      <div className="space-y-4">
        {sorted.map((card, i) => {
          const meta = TYPE_META[card.action_type] ?? TYPE_META.other;
          return (
            <div
              key={i}
              className={`bg-white rounded-xl border border-gray-200 border-l-4 ${meta.border} overflow-hidden`}
            >
              {/* Header */}
              <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${meta.badge}`}>
                    {meta.emoji} {meta.label}
                  </span>
                  <span className="text-sm font-semibold text-gray-900 truncate">{card.action}</span>
                </div>
                {/* Jira button + RICE score */}
                {card.rice && (
                  <div className="shrink-0 flex items-center gap-3">
                    <JiraButton card={card} />
                    <span className="text-xs text-gray-400 font-medium">RICE</span>
                    <span className="text-lg font-bold text-gray-900 leading-none">{card.rice.score}</span>
                  </div>
                )}
              </div>

              <div className="p-5 space-y-5">
                {/* RICE breakdown */}
                {card.rice && <RiceBar rice={card.rice} />}

                {/* Adaptive content */}
                <CardContent card={card} />

                {/* Supporting feedbacks */}
                {card.feedbacks.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                      Supporting feedbacks
                    </p>
                    <ul className="space-y-2.5">
                      {card.feedbacks.map((f, j) => {
                        const fb: SprintFeedback = typeof f === "string" ? { text: f } : f;
                        return (
                          <li key={j} className="flex gap-2">
                            <span className="text-gray-300 select-none shrink-0 mt-0.5">›</span>
                            <div>
                              <span className="text-sm text-gray-500 italic">"{fb.text}"</span>
                              {fb.translation && fb.translation.trim().toLowerCase() !== fb.text.trim().toLowerCase() && (
                                <p className="text-xs text-gray-400 mt-0.5 not-italic">
                                  🌐 {fb.translation}
                                </p>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
