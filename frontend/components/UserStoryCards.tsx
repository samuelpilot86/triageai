"use client";

import { UserStoryCard } from "@/lib/types";

const ACTION_COLORS = [
  "border-l-indigo-500",
  "border-l-violet-500",
  "border-l-sky-500",
];

export default function UserStoryCards({ cards }: { cards: UserStoryCard[] }) {
  if (!cards.length) return null;

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-gray-900">Key User Feedback</h2>
      <div className="space-y-4">
        {cards.map((card, i) => (
          <div
            key={i}
            className={`bg-white rounded-xl border border-gray-200 border-l-4 ${ACTION_COLORS[i] ?? "border-l-gray-300"} overflow-hidden`}
          >
            {/* Action title */}
            <div className="px-5 py-3 border-b border-gray-100">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide mr-2">
                Action {i + 1}
              </span>
              <span className="text-sm font-semibold text-gray-900">{card.action}</span>
            </div>

            <div className="p-5 space-y-5">
              {/* Supporting feedbacks */}
              <div className="space-y-2">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                  Supporting feedbacks
                </p>
                <ul className="space-y-1.5">
                  {card.feedbacks.map((f, j) => (
                    <li key={j} className="flex gap-2 text-sm text-gray-600">
                      <span className="text-gray-300 select-none mt-0.5">›</span>
                      <span className="italic">"{f}"</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* User stories */}
              <div className="space-y-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                  User {card.user_stories.length > 1 ? "stories" : "story"}
                </p>
                {card.user_stories.map((story, j) => (
                  <div key={j} className="space-y-2">
                    <p className="text-sm font-medium text-gray-800">{story.title}</p>
                    <ul className="space-y-1">
                      {story.acceptance_criteria.map((ac, k) => (
                        <li key={k} className="flex gap-2 text-xs text-gray-500">
                          <span className="text-indigo-400 font-bold select-none shrink-0">✓</span>
                          <span>{ac}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
