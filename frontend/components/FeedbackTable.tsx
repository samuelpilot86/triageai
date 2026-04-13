"use client";

import { FeedbackItem } from "@/lib/types";

const PRIORITY_BADGE: Record<string, string> = {
  High: "bg-red-100 text-red-700",
  Medium: "bg-amber-100 text-amber-700",
  Low: "bg-emerald-100 text-emerald-700",
};
const SENTIMENT_BADGE: Record<string, string> = {
  Positive: "bg-green-100 text-green-700",
  Neutral: "bg-gray-100 text-gray-600",
  Negative: "bg-red-100 text-red-600",
};
const CATEGORY_EMOJI: Record<string, string> = {
  "Bug / Error": "🐛",
  "Feature Request": "✨",
  "UX / Usability": "🎨",
  Performance: "⚡",
  Pricing: "💰",
  "Onboarding / Documentation": "📚",
  "Customer Support": "🎧",
  "Security / Privacy": "🔒",
  Other: "📌",
};

export default function FeedbackTable({ items }: { items: FeedbackItem[] }) {
  if (!items.length) return null;

  return (
    <div className="w-full overflow-x-auto rounded-xl border border-gray-200">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 w-8">#</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Summary</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Category</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Priority</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Reason</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Sentiment</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {items.map((item) => (
            <tr key={item.id} className="hover:bg-gray-50 transition-colors group">
              <td className="px-4 py-3 text-gray-400 text-xs">{item.id}</td>
              <td className="px-4 py-3">
                <span className="font-medium text-gray-800">{item.summary}</span>
                <p className="text-xs text-gray-400 mt-0.5 line-clamp-1 group-hover:line-clamp-none transition-all">
                  {item.original}
                </p>
              </td>
              <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                {CATEGORY_EMOJI[item.category] ?? "📌"} {item.category}
              </td>
              <td className="px-4 py-3">
                <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${PRIORITY_BADGE[item.priority] ?? ""}`}>
                  {item.priority}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-500 text-xs">{item.priority_reason}</td>
              <td className="px-4 py-3">
                <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${SENTIMENT_BADGE[item.sentiment] ?? ""}`}>
                  {item.sentiment}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
