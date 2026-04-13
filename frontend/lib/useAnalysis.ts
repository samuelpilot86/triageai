"use client";

import { useState, useCallback } from "react";
import { AnalysisStep, AnalysisResult, FeedbackItem, Correction, Store, AppEntry } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

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
      if (!cancelled) onError(e as Error);
    }
  })();

  return () => { cancelled = true; ctrl.abort(); };
}

export function useAnalysis() {
  const [step, setStep] = useState<AnalysisStep>({ type: "idle" });
  const [partialItems, setPartialItems] = useState<FeedbackItem[]>([]);

  const reset = useCallback(() => {
    setStep({ type: "idle" });
    setPartialItems([]);
  }, []);

  const handleEvents = useCallback((event: string, data: unknown) => {
    const d = data as Record<string, unknown>;
    if (event === "status") {
      const s = d.step as string;
      if (s === "scraping") setStep({ type: "scraping" });
      else if (s === "categorization") setStep({ type: "categorization" });
      else if (s === "report") setStep({ type: "report" });
    } else if (event === "categorization") {
      setPartialItems(d.items as FeedbackItem[]);
    } else if (event === "report") {
      setPartialItems((items) => {
        // finalize with report
        const result: AnalysisResult = {
          items,
          corrections: [] as Correction[],
          used_fallback: false,
          report: d.text as string,
          report_fallback: d.used_fallback as boolean,
        };
        setStep({ type: "done", result });
        return items;
      });
    } else if (event === "error") {
      setStep({ type: "error", message: d.message as string });
    }
  }, []);

  const analyzeText = useCallback((feedbacks: string[]) => {
    setStep({ type: "categorization" });
    setPartialItems([]);
    return streamEvents(
      `${API_BASE}/api/analyze/text`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedbacks }),
      },
      handleEvents,
      (e) => setStep({ type: "error", message: e.message })
    );
  }, [handleEvents]);

  const analyzeCsv = useCallback((file: File) => {
    setStep({ type: "categorization" });
    setPartialItems([]);
    const form = new FormData();
    form.append("file", file);
    return streamEvents(
      `${API_BASE}/api/analyze/csv`,
      { method: "POST", body: form },
      handleEvents,
      (e) => setStep({ type: "error", message: e.message })
    );
  }, [handleEvents]);

  const analyzeStore = useCallback((app: AppEntry, store: Store) => {
    setStep({ type: "scraping" });
    setPartialItems([]);
    return streamEvents(
      `${API_BASE}/api/analyze/store`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ app, store }),
      },
      handleEvents,
      (e) => setStep({ type: "error", message: e.message })
    );
  }, [handleEvents]);

  return { step, partialItems, analyzeText, analyzeCsv, analyzeStore, reset };
}
