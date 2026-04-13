"use client";

import { AnalysisResult, FeedbackItem } from "@/lib/types";

function StatPill({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium ${color}`}>
      <span>{value}</span>
      <span className="opacity-70">{label}</span>
    </div>
  );
}

function Stats({ items }: { items: FeedbackItem[] }) {
  const high = items.filter((i) => i.priority === "High").length;
  const medium = items.filter((i) => i.priority === "Medium").length;
  const low = items.filter((i) => i.priority === "Low").length;
  const positive = items.filter((i) => i.sentiment === "Positive").length;
  const negative = items.filter((i) => i.sentiment === "Negative").length;

  return (
    <div className="flex flex-wrap gap-2">
      <StatPill label="High" value={high} color="bg-red-100 text-red-700" />
      <StatPill label="Medium" value={medium} color="bg-amber-100 text-amber-700" />
      <StatPill label="Low" value={low} color="bg-emerald-100 text-emerald-700" />
      <div className="w-px bg-gray-200 mx-1" />
      <StatPill label="Positive" value={positive} color="bg-green-100 text-green-700" />
      <StatPill label="Negative" value={negative} color="bg-red-100 text-red-600" />
    </div>
  );
}

function renderMarkdown(text: string) {
  // Simple markdown renderer for the report (h2, bold, numbered lists)
  const lines = text.split("\n");
  return lines.map((line, i) => {
    if (line.startsWith("## ")) {
      return <h2 key={i} className="text-base font-semibold text-gray-900 mt-5 mb-2">{line.slice(3)}</h2>;
    }
    if (line.match(/^\d+\. /)) {
      const content = line.replace(/^\d+\. /, "").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      return <li key={i} className="text-sm text-gray-700 ml-4" dangerouslySetInnerHTML={{ __html: content }} />;
    }
    if (line.trim() === "") return <div key={i} className="h-1" />;
    const content = line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    return <p key={i} className="text-sm text-gray-700" dangerouslySetInnerHTML={{ __html: content }} />;
  });
}

function downloadCSV(items: FeedbackItem[]) {
  const headers = ["id", "original", "summary", "category", "priority", "priority_reason", "sentiment"];
  const rows = items.map((item) =>
    headers.map((h) => `"${String(item[h as keyof FeedbackItem] ?? "").replace(/"/g, '""')}"`).join(",")
  );
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "triageai_results.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function ReportPanel({ result }: { result: AnalysisResult }) {
  const { items, corrections, report, used_fallback, report_fallback } = result;

  return (
    <div className="space-y-8">
      {/* Stats row */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">{items.length} feedbacks analyzed</h2>
          <button
            onClick={() => downloadCSV(items)}
            className="text-xs text-indigo-600 hover:underline font-medium"
          >
            Export CSV
          </button>
        </div>
        <Stats items={items} />
        {(used_fallback || report_fallback) && (
          <p className="text-xs text-amber-600 bg-amber-50 px-3 py-1.5 rounded-lg">
            ⚠️ Gemini quota reached — analysis performed by Llama 3.3 70B (Groq). Results may vary slightly.
          </p>
        )}
      </div>

      {/* Corrections */}
      {corrections.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Auto-corrections ({corrections.length})</h3>
          {corrections.map((c, i) => (
            <div key={i} className="text-xs text-gray-600 bg-gray-50 px-3 py-2 rounded-lg">
              <span className="font-medium">#{c.id}</span> — {c.field}:{" "}
              <span className="line-through text-gray-400">{c.old_value}</span>{" "}
              → <span className="font-medium">{c.new_value}</span>{" "}
              <span className="text-gray-400">({c.reason})</span>
            </div>
          ))}
        </div>
      )}

      {/* Report */}
      {report && (
        <div className="border border-gray-200 rounded-xl p-5 space-y-1">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">Executive Report</h2>
          <ol className="list-none space-y-0.5">{renderMarkdown(report)}</ol>
        </div>
      )}
    </div>
  );
}
