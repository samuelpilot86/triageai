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
  }), []);

  const handleEvents = useCallback((event: string, data: unknown) => {
    const d = data as Record<string, unknown>;
    if (event === "status") {
      const s = d.step as string;
      if (s === "scraping") setStep({ type: "scraping" });
      else if (s === "report") {
        // Record categorization timing, then fetch report estimate
        if (categorizationStartRef.current !== null && nFeedbacksRef.current > 0) {
          const elapsed = Date.now() - categorizationStartRef.current;
          recordTiming("categorization", elapsed, nFeedbacksRef.current);
          categorizationStartRef.current = null;
        }
        fetchTimingEstimate("report").then((estimatedMs) => {
          const startedAt = Date.now();
          reportStartRef.current = startedAt;
          setStep({ type: "report", estimatedMs, startedAt });
        });
      }
      // "categorization" status is set by startCategorization with the estimate
    } else if (event === "scraped") {
      setStep((prev) =>
        prev.type === "categorization" ? prev : { type: "categorization" }
      );
    } else if (event === "categorization") {
      setPartialItems(d.items as FeedbackItem[]);
      correctionsRef.current = (d.corrections as Correction[]) ?? [];
      usedFallbackRef.current = (d.used_fallback as boolean) ?? false;
    } else if (event === "report") {
      // Record report timing
      if (reportStartRef.current !== null) {
        const elapsed = Date.now() - reportStartRef.current;
        recordTiming("report", elapsed);
        reportStartRef.current = null;
      }
      reportRef.current = {
        text: d.text as string,
        fallback: d.used_fallback as boolean,
      };
      // Update items with cluster info if present
      if (Array.isArray(d.items) && d.items.length > 0) {
        setPartialItems(d.items as FeedbackItem[]);
      }
      setPartialItems((items) => {
        setStep({ type: "done", result: buildResult(items) });
        return items;
      });
    } else if (event === "user_stories") {
      userStoryCardsRef.current = (d.cards as UserStoryCard[]) ?? [];
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

  return { step, partialItems, appName, analyzeText, analyzeCsv, analyzeStore, reset, retry };
}
