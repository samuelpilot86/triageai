"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";
const STORAGE_KEY = "triage.sift-eval.v1";

interface GoldenItem {
  id: number;
  text: string;
  actionable: boolean;
  reason: string;
}

interface GoldenSet {
  version: string;
  contract_size: number;
  recall_min: number;
  precision_min: number;
  item_count: number;
  actionable_count: number;
  chunk_count: number;
  items: GoldenItem[];
}

interface FailedChunk {
  index: number;
  size: number;
}

interface SiftResult {
  version: string;
  contract_size: number;
  recall_min: number;
  precision_min: number;
  item_count: number;
  actionable_count: number;
  chunk_count: number;
  failed_chunks: FailedChunk[];
  recall: number | null;
  precision: number | null;
  recall_hits: number;
  recall_total: number;
  precision_hits: number;
  precision_total: number;
  passed: boolean;
  reasons: string[];
  missed: GoldenItem[];
  kept_by_mistake: GoldenItem[];
  ran_at: string;
}

function formatRate(rate: number | null): string {
  if (rate == null) return "—";
  const percent = Math.round(rate * 1000) / 10;
  return Number.isInteger(percent) ? `${percent}%` : `${percent.toFixed(1)}%`;
}

function rateClass(rate: number | null, minimum: number): string {
  if (rate == null) return "text-gray-300";
  return rate >= minimum ? "text-emerald-600" : "text-red-600";
}

export default function SiftEvalPage() {
  const [setInfo, setSetInfo] = useState<GoldenSet | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<SiftResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/eval/sift`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await res.text());
        return res.json() as Promise<GoldenSet>;
      })
      .then((data) => {
        if (cancelled) return;
        setSetInfo(data);
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (!saved) return;
        try {
          const parsed = JSON.parse(saved) as SiftResult;
          if (parsed.version === data.version) setResult(parsed);
        } catch {
          window.localStorage.removeItem(STORAGE_KEY);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "The evaluation API is not reachable.");
      });
    return () => { cancelled = true; };
  }, []);

  async function run() {
    setRunning(true);
    setRunError(null);
    setProgress(null);
    try {
      const res = await fetch(`${API_BASE}/api/eval/sift/run`, { method: "POST" });
      if (!res.ok || !res.body) {
        const text = await res.text();
        let message = text || `HTTP ${res.status}`;
        try {
          const body = JSON.parse(text) as { detail?: unknown };
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          // The body was not JSON; show it as text.
        }
        throw new Error(message);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          let eventName = "message";
          let dataStr = "";
          for (const line of part.trim().split("\n")) {
            if (line.startsWith("event: ")) eventName = line.slice(7).trim();
            if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
          }
          if (!dataStr) continue;
          const data = JSON.parse(dataStr);
          if (eventName === "status") setProgress(data);
          if (eventName === "error") throw new Error(data.message || "Sift run failed");
          if (eventName === "result") {
            setResult(data);
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
          }
        }
      }
    } catch (err: unknown) {
      setRunError(err instanceof Error ? err.message : "Sift run failed");
    } finally {
      setRunning(false);
    }
  }

  function download() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `sift-eval-${result.version}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <img src="/logo.jpg" alt="trIAge logo" className="w-9 h-9 rounded-xl" />
            <div>
              <p className="text-lg font-semibold text-gray-900">trIAge</p>
              <p className="text-xs text-gray-400">Sift evaluation</p>
            </div>
          </Link>
          <Link
            href="/about"
            className="flex items-center gap-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 rounded-lg transition-colors"
          >
            🔧 Case study
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10 space-y-8">
        {loadError && (
          <p className="text-sm text-red-700 bg-red-50 px-4 py-3 rounded-xl">{loadError}</p>
        )}

        {setInfo && (
          <section className="bg-white border border-gray-200 rounded-xl p-6 space-y-3">
            <h1 className="text-lg font-semibold text-gray-900">Sift, on a frozen review set</h1>
            <p className="text-sm text-gray-600 leading-relaxed">
              Recall at least {formatRate(setInfo.recall_min)}, and precision at least {formatRate(setInfo.precision_min)}, on {setInfo.contract_size} reviews.
              This file is version {setInfo.version}: {setInfo.item_count} reviews, {setInfo.actionable_count} of them actionable, in {setInfo.chunk_count} chunk{setInfo.chunk_count === 1 ? "" : "s"} of 25.
            </p>
            <p className="text-sm text-gray-500 leading-relaxed">
              A green verdict needs the full set of {setInfo.contract_size}, both rates, and an answer from every chunk. A chunk that does not answer is left out of the rates.
            </p>
            <button
              onClick={run}
              disabled={running}
              className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold disabled:opacity-40 hover:bg-indigo-700 transition-colors"
            >
              {running ? "Running Sift…" : "Run Sift"}
            </button>
            {progress && (
              <p className="text-xs text-gray-500">{progress.done} of {progress.total} chunks answered</p>
            )}
          </section>
        )}

        {runError && (
          <p className="text-sm text-red-700 bg-red-50 px-4 py-3 rounded-xl">{runError}</p>
        )}

        {result && (
          <>
            <section className={`rounded-xl px-6 py-5 ${result.passed ? "bg-emerald-50" : "bg-red-50"}`}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className={`text-sm font-semibold ${result.passed ? "text-emerald-800" : "text-red-800"}`}>
                    {result.passed ? "Contract met" : "Contract not met"}
                  </h2>
                  {result.reasons.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {result.reasons.map((reason) => (
                        <li key={reason} className={`text-sm ${result.passed ? "text-emerald-700" : "text-red-700"}`}>{reason}</li>
                      ))}
                    </ul>
                  )}
                  <p className="text-xs text-gray-400 mt-3">Run at {new Date(result.ran_at).toLocaleString()}</p>
                </div>
                <button onClick={download} className="text-xs font-medium text-indigo-600 hover:underline shrink-0">
                  Download JSON
                </button>
              </div>
              <div className="grid grid-cols-2 gap-4 mt-5">
                <div>
                  <p className={`text-3xl font-bold ${rateClass(result.recall, result.recall_min)}`}>{formatRate(result.recall)}</p>
                  <p className="text-xs text-gray-500 mt-1">Recall · {result.recall_hits} of {result.recall_total} actionable reviews kept · need {formatRate(result.recall_min)}</p>
                </div>
                <div>
                  <p className={`text-3xl font-bold ${rateClass(result.precision, result.precision_min)}`}>{formatRate(result.precision)}</p>
                  <p className="text-xs text-gray-500 mt-1">Precision · {result.precision_hits} of {result.precision_total} kept reviews were actionable · need {formatRate(result.precision_min)}</p>
                </div>
              </div>
            </section>

            {result.failed_chunks.length > 0 && (
              <div className="text-sm text-amber-800 bg-amber-50 px-4 py-3 rounded-xl space-y-1">
                {result.failed_chunks.map((chunk) => (
                  <p key={chunk.index}>
                    Chunk {chunk.index} did not answer. Its {chunk.size} reviews were kept and are not counted as model errors.
                  </p>
                ))}
              </div>
            )}

            <ReviewList title="Missed" empty="No actionable review was dropped." items={result.missed} />
            <ReviewList title="Kept by mistake" empty="No non-actionable review was kept." items={result.kept_by_mistake} />
          </>
        )}
      </main>
    </div>
  );
}

function ReviewList({ title, empty, items }: { title: string; empty: string; items: GoldenItem[] }) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-gray-900">{title} ({items.length})</h2>
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        {items.length === 0 ? (
          <p className="px-4 py-3 text-sm text-gray-400">{empty}</p>
        ) : (
          <ul>
            {items.map((item) => (
              <li key={item.id} className="px-4 py-3 border-b border-gray-100 last:border-0">
                <p className="text-sm text-gray-800">{item.text}</p>
                <p className="text-xs text-gray-400 mt-1">{item.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
