"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Upload, ChevronDown } from "lucide-react";
import { Store, AppEntry } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

const PRIORITY_COLORS = {
  High: "bg-red-100 text-red-700",
  Medium: "bg-amber-100 text-amber-700",
  Low: "bg-emerald-100 text-emerald-700",
};

type Tab = "text" | "csv" | "store";

interface Props {
  onAnalyzeText: (feedbacks: string[]) => void;
  onAnalyzeCsv: (file: File) => void;
  onAnalyzeStore: (app: AppEntry, store: Store) => void;
  disabled?: boolean;
}

export default function InputPanel({ onAnalyzeText, onAnalyzeCsv, onAnalyzeStore, disabled }: Props) {
  const [tab, setTab] = useState<Tab>("text");
  const [text, setText] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [store, setStore] = useState<Store>("appstore");
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [apps, setApps] = useState<AppEntry[]>([]);
  const [selectedApp, setSelectedApp] = useState<AppEntry | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Fetch categories when store changes
  useEffect(() => {
    setSelectedCategory("");
    setSelectedApp(null);
    setApps([]);
    fetch(`${API_BASE}/api/store/categories?store=${store}`)
      .then((r) => r.json())
      .then((d) => setCategories(d.categories ?? []))
      .catch(() => {});
  }, [store]);

  // Fetch apps when category changes
  useEffect(() => {
    if (!selectedCategory) return;
    setSelectedApp(null);
    fetch(`${API_BASE}/api/store/apps?store=${store}&category=${encodeURIComponent(selectedCategory)}`)
      .then((r) => r.json())
      .then((d) => setApps(d.apps ?? []))
      .catch(() => {});
  }, [selectedCategory, store]);

  const handleFile = useCallback((file: File) => {
    if (file.name.endsWith(".csv")) setCsvFile(file);
  }, []);

  const feedbacks = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const canSubmitText = feedbacks.length >= 2 && !disabled;
  const canSubmitCsv = !!csvFile && !disabled;
  const canSubmitStore = !!selectedApp && !disabled;

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-6">
        {(["text", "csv", "store"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === t
                ? "border-b-2 border-indigo-600 text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "text" ? "Paste text" : t === "csv" ? "Upload CSV" : "App Store / Google Play"}
          </button>
        ))}
      </div>

      {/* Tab: Paste text */}
      {tab === "text" && (
        <div className="space-y-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"Paste your feedbacks here, one per line.\n\nExample:\nThe app crashes on startup\nDark mode is missing\nLoading is way too slow"}
            className="w-full h-52 px-4 py-3 text-sm rounded-xl border border-gray-200 bg-white resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 placeholder:text-gray-400"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">
              {feedbacks.length} feedback{feedbacks.length !== 1 ? "s" : ""}
              {feedbacks.length > 100 && " — first 100 will be analyzed"}
            </span>
            <button
              onClick={() => onAnalyzeText(feedbacks.slice(0, 100))}
              disabled={!canSubmitText}
              className="px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium disabled:opacity-40 hover:bg-indigo-700 transition-colors"
            >
              Analyze
            </button>
          </div>
        </div>
      )}

      {/* Tab: CSV upload */}
      {tab === "csv" && (
        <div className="space-y-3">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
            onClick={() => fileRef.current?.click()}
            className={`flex flex-col items-center justify-center gap-2 h-40 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
              dragOver ? "border-indigo-400 bg-indigo-50" : "border-gray-200 hover:border-gray-300 bg-white"
            }`}
          >
            <Upload className="w-6 h-6 text-gray-400" />
            {csvFile ? (
              <p className="text-sm font-medium text-gray-700">{csvFile.name}</p>
            ) : (
              <>
                <p className="text-sm text-gray-500">Drop a CSV file here or <span className="text-indigo-600 font-medium">browse</span></p>
                <p className="text-xs text-gray-400">Must have a <code>feedback</code> column (or first column is used)</p>
              </>
            )}
          </div>
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
          <div className="flex justify-end">
            <button
              onClick={() => csvFile && onAnalyzeCsv(csvFile)}
              disabled={!canSubmitCsv}
              className="px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium disabled:opacity-40 hover:bg-indigo-700 transition-colors"
            >
              Analyze
            </button>
          </div>
        </div>
      )}

      {/* Tab: Store */}
      {tab === "store" && (
        <div className="space-y-4">
          {/* Store toggle */}
          <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden">
            {(["appstore", "googleplay"] as Store[]).map((s) => (
              <button
                key={s}
                onClick={() => setStore(s)}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  store === s ? "bg-indigo-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {s === "googleplay" ? "Google Play" : "App Store"}
              </button>
            ))}
          </div>

          {/* Category dropdown */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Category</label>
            <div className="relative">
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="w-full appearance-none px-3 py-2 pr-8 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select a category…</option>
                {categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* App dropdown */}
          {apps.length > 0 && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Application</label>
              <div className="relative">
                <select
                  value={selectedApp ? String(selectedApp.id) : ""}
                  onChange={(e) => setSelectedApp(apps.find((a) => String(a.id) === e.target.value) ?? null)}
                  className="w-full appearance-none px-3 py-2 pr-8 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Select an app…</option>
                  {apps.map((a) => <option key={String(a.id)} value={String(a.id)}>{a.name}</option>)}
                </select>
                <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={() => selectedApp && onAnalyzeStore(selectedApp, store)}
              disabled={!canSubmitStore}
              className="px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium disabled:opacity-40 hover:bg-indigo-700 transition-colors"
            >
              Fetch &amp; Analyze
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
