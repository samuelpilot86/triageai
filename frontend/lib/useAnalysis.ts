"use client";

import { useState, useCallback, useRef } from "react";
import { AnalysisStep, AnalysisResult, FeedbackItem, Correction, Store, AppEntry, UserStoryCard } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

// ------------------------------------------------------------------
// Timing helpers
// ------------------------------------------------------------------

const FALLBACK_MS_PER_FEEDBACK = 200;
const FALLBACK_REPORT_MS = 15_000;

async function fetchTimingEstimate(step: "categorization" | "report", n?: number): Promise<number> {
  try {
    const res = await fetch(`${API_BASE}/api/timings?step=${step}`);
    if (!res.ok) throw new Error();
    const { timings } = await res.json() as { timings: { ms: number; n?: number }[] };
    if (!timings.length) throw new Error();
    if (step === "categorization" && n) {
      const avgMsPerFeedback = timings.reduce((sum, t) => sum + t.ms / (t.n ?? n), 0) / timings.length;
      return Math.round(n * avgMsPerFeedback);
    }
    // For report: simple average of raw durations (not per-feedback)
    return Math.round(timings.reduce((sum, t) => sum + t.ms, 0) / timings.length);
  } catch {
    return step === "categorization"
      ? (n ?? 50) * FALLBACK_MS_PER_FEEDBACK
      : FALLBACK_REPORT_MS;
  }
}

function recordTiming(step: "categorization" | "report", ms: number, n?: number): void {
  fetch(`${API_BASE}/api/timings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step, ms, ...(n !== undefined ? { n } : {}) }),
  }).catch(() => {});
}

// ------------------------------------------------------------------
// SSE streaming
// ------------------------------------------------------------------

function streamEvents(
  url: string,
  options: RequestInit,
  onEvent: (event: string, data: unknown) => void,
  onError: (err: Error) => void
): () => void {
  let cancelled = false;
  const ctrl = new AbortController();

  (async () => {
    try {
      const res = await fetch(url, { ...options, signal: ctrl.signal });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done || cancelled) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const lines = part.trim().split("\n");
          let eventName = "message";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) eventName = line.slice(7).trim();
            if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
          }
          if (dataStr) {
            try { onEvent(eventName, JSON.parse(dataStr)); }
            catch { onEvent(eventName, dataStr); }
          }
        }
      }
    } catch (e) {
      if (!cancelled) {
        const msg = (e instanceof Error)
          ? `${e.name}: ${e.message || "(no message)"} — stack: ${e.stack?.split("\n")[1] ?? ""}`
          : String(e);
        console.error("[trIAge SSE error]", msg, e);
        onError(new Error(msg));
      }
    }
  })();

  return () => { cancelled = true; ctrl.abort(); };
}

// ------------------------------------------------------------------
// Hook
// ------------------------------------------------------------------

export function useAnalysis() {
  const [step, setStep] = useState<AnalysisStep>({ type: "idle" });
  const [partialItems, setPartialItems] = useState<FeedbackItem[]>([]);
  const [appName, setAppName] = useState<string | null>(null);
  const correctionsRef = useRef<Correction[]>([]);
  const usedFallbackRef = useRef<boolean>(false);
  const reportRef = useRef<{ text: string; fallback: boolean } | null>(null);
  const userStoryCardsRef = useRef<UserStoryCard[]>([]);
  const nonActionableItemsRef = useRef<string[]>([]);
  const actionableCountRef = useRef<number | null>(null);
  const categorizationStartRef = useRef<number | null>(null);
  const reportStartRef = useRef<number | null>(null);
  const nFeedbacksRef = useRef<number>(0);
  const lastCallRef = useRef<(() => (() => void) | Promise<() => void>) | null>(null);

  const reset = useCallback(() => {
    setStep({ type: "idle" });
    setPartialItems([]);
    setAppName(null);
    correctionsRef.current = [];
    usedFallbackRef.current = false;
    reportRef.current = null;
    userStoryCardsRef.current = [];
    nonActionableItemsRef.current = [];
    actionableCountRef.current = null;
    categorizationStartRef.current = null;
    reportStartRef.current = null;
    nFeedbacksRef.current = 0;
  }, []);

  const buildResult = useCallback((items: FeedbackItem[]): AnalysisResult => ({
    items,
    corrections: correctionsRef.current,
    used_fallback: usedFallbackRef.current,
    report: reportRef.current?.text ?? "",
    report_fallback: reportRef.current?.fallback ?? false,
    user_story_cards: userStoryCardsRef.current,
    non_actionable_items: nonActionableItemsRef.current,
  }), []);

  const handleEvents = useCallback((event: string, data: unknown) => {
    const d = data as Record<string, unknown>;
    if (event === "status") {
      const s = d.step as string;
      if (s === "scraping") setStep({ type: "scraping" });
      else if (s === "sift") setStep({ type: "sift", startedAt: Date.now(), estimatedMs: 5000 });
      else if (s === "report") {
        // Set step immediately so Penn card activates without waiting for the fetch
        const startedAt = Date.now();
        reportStartRef.current = startedAt;
        setStep({ type: "report", startedAt });
        // Record categorization timing
        if (categorizationStartRef.current !== null && nFeedbacksRef.current > 0) {
          const elapsed = startedAt - categorizationStartRef.current;
          recordTiming("categorization", elapsed, nFeedbacksRef.current);
          categorizationStartRef.current = null;
        }
        // Fetch estimate and fill it in once available
        fetchTimingEstimate("report").then((estimatedMs) => {
          setStep((prev) => prev.type === "report" ? { ...prev, estimatedMs } : prev);
        });
      }
      else if (s === "clustering") {
        // Start Echo timer + fetch estimate (cluster timing not persisted, use fixed fallback)
        const startedAt = Date.now();
        setStep({ type: "clustering", startedAt, estimatedMs: 8_000 });
      }
      else if (s === "stella") {
        // Nova is now active — keep it distinct from Penn
        setStep({ type: "stella", startedAt: Date.now() });
      }
    } else if (event === "sifted") {
      nonActionableItemsRef.current = (d.non_actionable as string[]) ?? [];
      actionableCountRef.current = d.actionable_count as number;
      nFeedbacksRef.current = d.actionable_count as number;
    } else if (event === "scraped") {
      setStep((prev) =>
        prev.type === "categorization" ? prev : { type: "categorization" }
      );
    } else if (event === "clustered") {
      setStep({ type: "clustering", clusterCount: d.count as number });
      if (Array.isArray(d.items) && d.items.length > 0) {
        setPartialItems(d.items as FeedbackItem[]);
      }
    } else if (event === "categorization") {
      const fallback = (d.used_fallback as boolean) ?? false;
      setPartialItems(d.items as FeedbackItem[]);
      correctionsRef.current = (d.corrections as Correction[]) ?? [];
      usedFallbackRef.current = fallback;
      setStep((prev) => prev.type === "categorization" ? { ...prev, usedFallback: fallback } : prev);
    } else if (event === "report") {
      // Record Penn timing; keep step open — Nova may still run
      if (reportStartRef.current !== null) {
        const elapsed = Date.now() - reportStartRef.current;
        recordTiming("report", elapsed);
        reportStartRef.current = null;
      }
      reportRef.current = {
        text: d.text as string,
        fallback: d.used_fallback as boolean,
      };
    } else if (event === "user_stories") {
      userStoryCardsRef.current = (d.cards as UserStoryCard[]) ?? [];
      setPartialItems((items) => {
        setStep({ type: "done", result: buildResult(items) });
        return items;
      });
    } else if (event === "done") {
      // Final signal from backend — handles the no-actions case where Nova is skipped
      setPartialItems((items) => {
        setStep({ type: "done", result: buildResult(items) });
        return items;
      });
    } else if (event === "error") {
      setStep({ type: "error", message: d.message as string });
    }
  }, [buildResult]);

  // Sets categorization step with timing estimate, then kicks off SSE
  const startCategorization = useCallback(async (
    n: number,
    launchStream: () => () => void
  ) => {
    const estimatedMs = await fetchTimingEstimate("categorization", n);
    const startedAt = Date.now();
    categorizationStartRef.current = startedAt;
    nFeedbacksRef.current = n;
    setStep({ type: "categorization", estimatedMs, startedAt, nFeedbacks: n });
    setPartialItems([]);
    return launchStream();
  }, []);

  const analyzeText = useCallback((feedbacks: string[], name?: string) => {
    setAppName(name ?? null);
    const call = () => startCategorization(feedbacks.length, () =>
      streamEvents(
        `${API_BASE}/api/analyze/text`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedbacks }),
        },
        handleEvents,
        (e) => setStep({ type: "error", message: e.message })
      )
    );
    lastCallRef.current = call;
    return call();
  }, [handleEvents, startCategorization]);

  const analyzeCsv = useCallback((file: File) => {
    // CSV: we don't know n upfront, use 50 as estimate placeholder
    const call = () => startCategorization(50, () => {
      const form = new FormData();
      form.append("file", file);
      return streamEvents(
        `${API_BASE}/api/analyze/csv`,
        { method: "POST", body: form },
        handleEvents,
        (e) => setStep({ type: "error", message: e.message })
      );
    });
    lastCallRef.current = call;
    return call();
  }, [handleEvents, startCategorization]);

  const analyzeStore = useCallback((app: AppEntry, store: Store, count: number = 100) => {
    setAppName(app.name ?? null);
    // Store: scraping phase first, categorization estimate set when scraped arrives
    const call = () => {
      setStep({ type: "scraping" });
      setPartialItems([]);
      categorizationStartRef.current = null;
      nFeedbacksRef.current = count;
      return streamEventsInner();
    };
    const streamEventsInner = () => streamEvents(
      `${API_BASE}/api/analyze/store`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ app, store, count }),
      },
      async (event, data) => {
        // When scraping done, switch to categorization with estimate
        if (event === "scraped") {
          const count = (data as Record<string, unknown>).count as number ?? 100;
          const estimatedMs = await fetchTimingEstimate("categorization", count);
          const startedAt = Date.now();
          categorizationStartRef.current = startedAt;
          nFeedbacksRef.current = count;
          setStep({ type: "categorization", estimatedMs, startedAt, nFeedbacks: count, scrapedCount: count });
        } else {
          handleEvents(event, data);
        }
      },
      (e) => setStep({ type: "error", message: e.message })
    );
    lastCallRef.current = call;
    return call();
  }, [handleEvents]);

  const retry = useCallback(() => {
    if (lastCallRef.current) return lastCallRef.current();
  }, []);

  return { step, partialItems, appName, nonActionableItemsRef, actionableCountRef, analyzeText, analyzeCsv, analyzeStore, reset, retry };
}
