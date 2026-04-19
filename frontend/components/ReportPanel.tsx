"use client";

import { AnalysisResult, FeedbackItem } from "@/lib/types";

// ------------------------------------------------------------------
// Shared helpers
// ------------------------------------------------------------------

function StatPill({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium ${color}`}>
      <span>{value}</span>
      <span className="opacity-70">{label}</span>
    </div>
  );
}

function renderMarkdown(text: string) {
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
  const headers = ["id", "original", "summary", "category", "priority", "priority_reason", "cluster_label"];
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

// ------------------------------------------------------------------
// Exported sub-components
// ------------------------------------------------------------------

export function FeedbackStats({ items }: { items: FeedbackItem[] }) {
  const high = items.filter((i) => i.priority === "High").length;
  const medium = items.filter((i) => i.priority === "Medium").length;
  const low = items.filter((i) => i.priority === "Low").length;

  return (
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
      <div className="flex flex-wrap gap-2">
        <StatPill label="High" value={high} color="bg-red-100 text-red-700" />
        <StatPill label="Medium" value={medium} color="bg-amber-100 text-amber-700" />
        <StatPill label="Low" value={low} color="bg-emerald-100 text-emerald-700" />
      </div>
    </div>
  );
}

export function FallbackBanner({ used_fallback, report_fallback }: { used_fallback: boolean; report_fallback: boolean }) {
  if (!used_fallback && !report_fallback) return null;
  return (
    <p className="text-xs text-amber-600 bg-amber-50 px-3 py-1.5 rounded-lg">
      ⚠️ Primary provider quota reached — analysis performed by a fallback model. Results may vary slightly.
    </p>
  );
}

export function ExecutiveReport({ report }: { report: string }) {
  if (!report) return null;
  return (
    <div className="border border-gray-200 rounded-xl p-6 space-y-1">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-lg">🖊️</span>
        <h2 className="text-xl font-bold tracking-tight text-gray-900">Executive Report</h2>
      </div>
      <ol className="list-none space-y-0.5">{renderMarkdown(report)}</ol>
    </div>
  );
}

export function IrisCorrections({ result }: { result: AnalysisResult }) {
  const { items, corrections: rawCorrections } = result;
  const corrections = rawCorrections.filter((c) => c.old_value !== c.new_value);

  return (
    <details className="space-y-1.5 group">
      <summary className="cursor-pointer list-none text-xs font-semibold text-gray-500 uppercase tracking-wide hover:text-gray-700 select-none">
        <span className="inline-block transition-transform group-open:rotate-90 mr-1">▸</span>
        Iris self-corrections {corrections.length > 0 ? `(${corrections.length})` : `(0 — all ${items.length} feedbacks OK)`}
      </summary>
      <div className="space-y-1.5 mt-2">
        {corrections.length === 0 ? (
          <p className="text-xs text-emerald-600 bg-emerald-50 px-3 py-2 rounded-lg">
            ✓ All {items.length} feedbacks reviewed across category and priority — no corrections needed.
          </p>
        ) : (
          corrections.map((c, i) => (
            <div key={i} className="text-xs text-gray-600 bg-gray-50 px-3 py-2 rounded-lg">
              <span className="font-medium">#{c.id}</span> — {c.field}:{" "}
              <span className="line-through text-gray-400">{String(c.old_value)}</span>{" "}
              → <span className="font-medium text-indigo-600">{String(c.new_value)}</span>{" "}
              <span className="text-gray-400">({c.reason})</span>
            </div>
          ))
        )}
      </div>
    </details>
  );
}

// ------------------------------------------------------------------
// Default export (unused by page.tsx but kept for safety)
// ------------------------------------------------------------------

export default function ReportPanel({ result }: { result: AnalysisResult }) {
  return (
    <div className="space-y-8">
      <FeedbackStats items={result.items} />
      <FallbackBanner used_fallback={result.used_fallback} report_fallback={result.report_fallback} />
      <ExecutiveReport report={result.report} />
      <IrisCorrections result={result} />
    </div>
  );
}
