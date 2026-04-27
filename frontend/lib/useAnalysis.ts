"use client";

import { useState, useCallback, useRef } from "react";
import { AnalysisStep, AnalysisResult, FeedbackItem, Correction, Store, AppEntry, UserStoryCard } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

// ------------------------------------------------------------------
// Timing helpers
// ------------------------------------------------------------------

const FALLBACK_MS_PER_FEEDBACK = 200;
const FALLBACK_REPORT_MS = 15_000;

// Must stay in sync with backend agent.py constants
const SIFT_CHUNK_SIZE = 25;
const GROQ_CHUNK_SIZE = 30;

type TimingStep = "sift" | "categorization" | "clustering" | "report" | "stella";

const FALLBACK_MS: Record<TimingStep, number> = {
  sift: 8_000,
  categorization: 15_000,
  clustering: 8_000,
  report: 15_000,
  stella: 10_000,
};

async function fetchTimingEstimate(step: TimingStep, n?: number): Promise<number> {
  try {
    const res = await fetch(`${API_BASE}/api/timings?step=${step}`);
    if (!res.ok) throw new Error();
    const { timings } = await res.json() as { timings: { ms: number; n?: number }[] };
    if (!timings.length) throw new Error();
    // Batched parallel steps: wall-clock ≈ time for the largest chunk
    if (step === "categorization" && n) {
      const effectiveN = Math.min(n, GROQ_CHUNK_SIZE);
      const avgMsPerFeedback = timings.reduce((sum, t) => sum + t.ms / (t.n ?? effectiveN), 0) / timings.length;
      return Math.round(effectiveN * avgMsPerFeedback);
    }
    if (step === "sift" && n) {
      const effectiveN = Math.min(n, SIFT_CHUNK_SIZE);
      const avgMsPerFeedback = timings.reduce((sum, t) => sum + t.ms / (t.n ?? effectiveN), 0) / timings.length;
      return Math.round(effectiveN * avgMsPerFeedback);
    }
    // clustering, report, stella: flat average
    return Math.round(timings.reduce((sum, t) => sum + t.ms, 0) / timings.length);
  } catch {
    if (step === "categorization" && n) return Math.min(n, GROQ_CHUNK_SIZE) * FALLBACK_MS_PER_FEEDBACK;
    if (step === "sift" && n) return Math.min(n, SIFT_CHUNK_SIZE) * FALLBACK_MS_PER_FEEDBACK;
    return FALLBACK_MS[step];
  }
}

function recordTiming(step: TimingStep, ms: number, n?: number): void {
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
  const irisFallbackProviderRef = useRef<string | null>(null);
  const reportRef = useRef<{ text: string; fallback: boolean; fallback_provider?: string | null } | null>(null);
  const userStoryCardsRef = useRef<UserStoryCard[]>([]);
  const nonActionableItemsRef = useRef<string[]>([]);
  const actionableCountRef = useRef<number | null>(null);
  const siftStartRef = useRef<number | null>(null);
  const siftNRef = useRef<number>(0);
  const categorizationStartRef = useRef<number | null>(null);
  const clusteringStartRef = useRef<number | null>(null);
  const reportStartRef = useRef<number | null>(null);
  const stellaStartRef = useRef<number | null>(null);
  const nFeedbacksRef = useRef<number>(0);
  const lastCallRef = useRef<(() => (() => void) | Promise<() => void>) | null>(null);
  const allEstimatesRef = useRef<Partial<Record<TimingStep, number>>>({});

  const reset = useCallback(() => {
    setStep({ type: "idle" });
    setPartialItems([]);
    setAppName(null);
    correctionsRef.current = [];
    usedFallbackRef.current = false;
    irisFallbackProviderRef.current = null;
    reportRef.current = null;
    userStoryCardsRef.current = [];
    nonActionableItemsRef.current = [];
    actionableCountRef.current = null;
    siftStartRef.current = null;
    siftNRef.current = 0;
    categorizationStartRef.current = null;
    clusteringStartRef.current = null;
    reportStartRef.current = null;
    stellaStartRef.current = null;
    nFeedbacksRef.current = 0;
    allEstimatesRef.current = {};
  }, []);

  const cardsProviderRef = useRef<string | null>(null);

  const buildResult = useCallback((items: FeedbackItem[]): AnalysisResult => ({
    items,
    corrections: correctionsRef.current,
    used_fallback: usedFallbackRef.current,
    iris_fallback_provider: irisFallbackProviderRef.current,
    report: reportRef.current?.text ?? "",
    report_fallback: reportRef.current?.fallback ?? false,
    report_fallback_provider: reportRef.current?.fallback_provider ?? null,
    cards_fallback_provider: cardsProviderRef.current,
    user_story_cards: userStoryCardsRef.current,
    non_actionable_items: nonActionableItemsRef.current,
  }), []);

  const handleEvents = useCallback((event: string, data: unknown) => {
    const d = data as Record<string, unknown>;
    if (event === "status") {
      const s = d.step as string;
      if (s === "scraping") setStep({ type: "scraping" });
      else if (s === "sift") {
        const startedAt = Date.now();
        siftStartRef.current = startedAt;
        siftNRef.current = nFeedbacksRef.current; // raw input count, known before sift
        // Fetch historical estimate, fill it in once available
        fetchTimingEstimate("sift", nFeedbacksRef.current).then((estimatedMs) => {
          setStep((prev) => prev.type === "sift" ? { ...prev, estimatedMs } : prev);
        });
        setStep({ type: "sift", startedAt });
      }
      else if (s === "categorization") {
        // Iris is now genuinely active — reset startedAt to the real start time
        const startedAt = Date.now();
        categorizationStartRef.current = startedAt;
        setStep((prev) => {
          const estimatedMs = prev.type === "categorization" ? prev.estimatedMs : undefined;
          return { type: "categorization", startedAt, estimatedMs, nFeedbacks: nFeedbacksRef.current };
        });
      }
      else if (s === "clustering") {
        const startedAt = Date.now();
        clusteringStartRef.current = startedAt;
        // Record categorization timing (Iris just finished)
        if (categorizationStartRef.current !== null && nFeedbacksRef.current > 0) {
          const elapsed = startedAt - categorizationStartRef.current;
          recordTiming("categorization", elapsed, Math.min(nFeedbacksRef.current, GROQ_CHUNK_SIZE));
          categorizationStartRef.current = null;
        }
        fetchTimingEstimate("clustering").then((estimatedMs) => {
          setStep((prev) => prev.type === "clustering" ? { ...prev, estimatedMs } : prev);
        });
        setStep({ type: "clustering", startedAt });
      }
      else if (s === "report") {
        const startedAt = Date.now();
        reportStartRef.current = startedAt;
        // Record clustering timing (Echo just finished)
        if (clusteringStartRef.current !== null) {
          const elapsed = startedAt - clusteringStartRef.current;
          recordTiming("clustering", elapsed);
          clusteringStartRef.current = null;
        }
        setStep({ type: "report", startedAt });
        fetchTimingEstimate("report").then((estimatedMs) => {
          setStep((prev) => prev.type === "report" ? { ...prev, estimatedMs } : prev);
        });
      }
      else if (s === "stella") {
        const startedAt = Date.now();
        stellaStartRef.current = startedAt;
        // Record Penn timing (report event fires before stella status)
        fetchTimingEstimate("stella").then((estimatedMs) => {
          setStep((prev) => prev.type === "stella" ? { ...prev, estimatedMs } : prev);
        });
        setStep({ type: "stella", startedAt });
      }
    } else if (event === "sifted") {
      // Sift finished — record timing
      if (siftStartRef.current !== null) {
        const elapsed = Date.now() - siftStartRef.current;
        recordTiming("sift", elapsed, Math.min(siftNRef.current, SIFT_CHUNK_SIZE));
        siftStartRef.current = null;
      }
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
      irisFallbackProviderRef.current = (d.fallback_provider as string | null) ?? null;
      setStep((prev) => prev.type === "categorization" ? { ...prev, usedFallback: fallback } : prev);
    } else if (event === "report") {
      // Penn finished — record timing
      if (reportStartRef.current !== null) {
        const elapsed = Date.now() - reportStartRef.current;
        recordTiming("report", elapsed);
        reportStartRef.current = null;
      }
      reportRef.current = {
        text: d.text as string,
        fallback: d.used_fallback as boolean,
        fallback_provider: (d.fallback_provider as string | null) ?? null,
      };
    } else if (event === "user_stories") {
      // Nova finished — record timing
      if (stellaStartRef.current !== null) {
        const elapsed = Date.now() - stellaStartRef.current;
        recordTiming("stella", elapsed);
        stellaStartRef.current = null;
      }
      userStoryCardsRef.current = (d.cards as UserStoryCard[]) ?? [];
      cardsProviderRef.current = (d.fallback_provider as string | null) ?? null;
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

  // Pre-fetch all step estimates at analysis launch so they can be shown upfront
  const prefetchAllEstimates = useCallback(async (n: number) => {
    const steps: TimingStep[] = ["sift", "categorization", "clustering", "report", "stella"];
    const results = await Promise.all(steps.map((s) => fetchTimingEstimate(s, n)));
    const estimates: Partial<Record<TimingStep, number>> = {};
    steps.forEach((s, i) => { estimates[s] = results[i]; });
    allEstimatesRef.current = estimates;
  }, []);

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
    prefetchAllEstimates(feedbacks.length);
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
    prefetchAllEstimates(50);
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
    prefetchAllEstimates(count);
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

  return { step, partialItems, appName, nonActionableItemsRef, actionableCountRef, allEstimatesRef, analyzeText, analyzeCsv, analyzeStore, reset, retry };
}
