"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Upload, ChevronDown, ClipboardList, FileSpreadsheet, Star, Zap, Search, Loader2 } from "lucide-react";
import { Store, AppEntry } from "@/lib/types";
import { DEMO_FEEDBACKS } from "@/lib/demoFeedbacks";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

type Tab = "text" | "csv" | "store" | "demo";

interface Props {
  onAnalyzeText: (feedbacks: string[], appName?: string) => void;
  onAnalyzeCsv: (file: File) => void;
  onAnalyzeStore: (app: AppEntry, store: Store, count: number) => void;
  disabled?: boolean;
}


const TAB_META: Record<Tab, { label: string; icon: React.ReactNode }> = {
  store: {
    label: "App Store / Google Play",
    icon: <Star className="w-4 h-4" />,
  },
  text: {
    label: "Paste feedback",
    icon: <ClipboardList className="w-4 h-4" />,
  },
  csv: {
    label: "Upload CSV",
    icon: <FileSpreadsheet className="w-4 h-4" />,
  },
  demo: {
    label: "Demo",
    icon: <Zap className="w-4 h-4" />,
  },
};

export default function InputPanel({ onAnalyzeText, onAnalyzeCsv, onAnalyzeStore, disabled }: Props) {
  const [tab, setTab] = useState<Tab>("demo");
  const [text, setText] = useState("");
  const [demoText, setDemoText] = useState(DEMO_FEEDBACKS);
  const [dragOver, setDragOver] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [store, setStore] = useState<Store>("googleplay");
  const [reviewCount, setReviewCount] = useState<number>(100);
  const [categories, setCategories] = useState<string[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [categoriesError, setCategoriesError] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [apps, setApps] = useState<AppEntry[]>([]);
  const [selectedApp, setSelectedApp] = useState<AppEntry | null>(null);
  const [appIsOther, setAppIsOther] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<AppEntry[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Reset count when switching store
  useEffect(() => {
    setReviewCount(store === "appstore" ? 50 : 100);
  }, [store]);

  // Fetch categories when store changes
  const loadCategories = useCallback(() => {
    setCategoriesLoading(true);
    setCategoriesError(false);
    fetch(`${API_BASE}/api/store/categories?store=${store}`)
      .then((r) => r.json())
      .then((d) => {
        const cats = d.categories ?? [];
        setCategories(cats);
        if (cats.length === 0) setCategoriesError(true);
      })
      .catch(() => setCategoriesError(true))
      .finally(() => setCategoriesLoading(false));
  }, [store]);

  useEffect(() => {
    setSelectedCategory("");
    setSelectedApp(null);
    setApps([]);
    setAppIsOther(false);
    setSearchQuery("");
    setSearchResults([]);
    loadCategories();
  }, [store, loadCategories]);

  // Fetch top apps when category changes
  useEffect(() => {
    if (!selectedCategory) return;
    setSelectedApp(null);
    setAppIsOther(false);
    setSearchQuery("");
    setSearchResults([]);
    fetch(`${API_BASE}/api/store/apps?store=${store}&category=${encodeURIComponent(selectedCategory)}`)
      .then((r) => r.json())
      .then((d) => setApps(d.apps ?? []))
      .catch(() => {});
  }, [selectedCategory, store]);

  // Debounced search on query change
  useEffect(() => {
    if (!searchQuery.trim()) { setSearchResults([]); return; }
    // Skip search if query already matches selected app (just picked from list)
    if (selectedApp && selectedApp.name === searchQuery) return;
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setIsSearching(true);
      fetch(`${API_BASE}/api/store/search?store=${store}&q=${encodeURIComponent(searchQuery)}`)
        .then((r) => r.json())
        .then((d) => setSearchResults(d.apps ?? []))
        .catch(() => {})
        .finally(() => setIsSearching(false));
    }, 400);
  }, [searchQuery, selectedApp, store]);

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
        {(["store", "csv", "text", "demo"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
              tab === t
                ? "border-b-2 border-indigo-600 text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {TAB_META[t].icon}
            {TAB_META[t].label}
          </button>
        ))}
      </div>

      {/* Tab: Paste feedback */}
      {tab === "text" && (
        <div className="space-y-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"Paste your user feedbacks here, one per line.\n\nExample:\n\"The app crashes every time I try to log in...\"\n\"Love the new design but the export button is broken...\"\n\"Loading takes forever, please fix this\""}
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
              className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold disabled:opacity-40 hover:bg-indigo-700 transition-colors shadow-sm"
            >
              Analyze feedbacks →
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
              className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold disabled:opacity-40 hover:bg-indigo-700 transition-colors shadow-sm"
            >
              Analyze feedbacks →
            </button>
          </div>
        </div>
      )}

      {/* Tab: Demo */}
      {tab === "demo" && (
        <div className="space-y-3">
          <textarea
            value={demoText}
            onChange={(e) => setDemoText(e.target.value)}
            disabled={disabled}
            className="w-full h-52 px-4 py-3 text-sm rounded-xl border border-gray-200 bg-gray-50 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-500 disabled:opacity-60"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">100 real ChatGPT reviews (Google Play, en-US) — edit to remove some</span>
            <button
              onClick={() => onAnalyzeText(demoText.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 100), "ChatGPT")}
              disabled={disabled || demoText.split("\n").filter((l) => l.trim()).length < 2}
              className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold disabled:opacity-40 hover:bg-indigo-700 transition-colors shadow-sm"
            >
              <Zap className="w-4 h-4" />
              Run demo →
            </button>
          </div>
        </div>
      )}

      {/* Tab: Store */}
      {tab === "store" && (
        <div className="space-y-4">
          {/* Row 1: store toggle + reviews-to-fetch */}
          <div className="flex items-end justify-between gap-3 flex-wrap">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Store</label>
              <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden">
                {(["googleplay", "appstore"] as Store[]).map((s) => (
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
            </div>

            <div className="min-w-[180px]">
              <label className="block text-xs font-medium text-gray-500 mb-1">Reviews to fetch</label>
              {store === "appstore" ? (
                <p className="text-sm text-gray-500 px-3 py-2 rounded-lg border border-gray-100 bg-gray-50">
                  50 <span className="text-xs text-gray-400">(Apple RSS limit)</span>
                </p>
              ) : (
                <div className="relative">
                  <select
                    value={reviewCount}
                    onChange={(e) => setReviewCount(Number(e.target.value))}
                    className="w-full appearance-none px-3 py-2 pr-8 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {[50, 100].map((n) => (
                      <option key={n} value={n}>{n} reviews</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
                </div>
              )}
            </div>
          </div>

          {/* Zone A: search by app name */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2">
            <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wide">Search by app name</label>
            <div className="relative">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setSelectedApp(null);
                  // Clear category browse selection when user types in search
                  if (e.target.value.trim()) setSelectedCategory("");
                }}
                onFocus={() => setAppIsOther(true)}
                placeholder="e.g. Spotify, Notion, Duolingo…"
                className="w-full pl-9 pr-9 py-2 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              {isSearching && <Loader2 className="absolute right-3 top-2.5 w-4 h-4 text-gray-400 animate-spin" />}
            </div>
            {searchResults.length > 0 && (
              <div className="border border-gray-200 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
                {searchResults.map((a) => (
                  <button
                    key={String(a.id)}
                    onClick={() => { setSelectedApp(a); setSearchQuery(a.name); setSearchResults([]); }}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      selectedApp?.id === a.id
                        ? "bg-indigo-50 text-indigo-700 font-medium"
                        : "hover:bg-gray-50 text-gray-700"
                    }`}
                  >
                    {a.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* OR separator */}
          <div className="flex items-center gap-3 text-xs text-gray-400">
            <div className="flex-1 h-px bg-gray-200" />
            <span className="uppercase tracking-wide">or</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          {/* Zone B: browse by category */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
            <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wide">Browse by category</label>

            {categoriesError ? (
              <div className="flex items-center justify-between px-3 py-2 rounded-lg border border-red-200 bg-red-50 text-xs text-red-600">
                <span>Failed to load categories — backend may be starting up</span>
                <button
                  onClick={loadCategories}
                  className="ml-2 font-semibold underline hover:no-underline shrink-0"
                >
                  Retry
                </button>
              </div>
            ) : (
              <div className="relative">
                <select
                  value={selectedCategory}
                  onChange={(e) => {
                    setSelectedCategory(e.target.value);
                    // Clear search zone when picking a category
                    if (e.target.value) {
                      setSearchQuery("");
                      setSearchResults([]);
                      setAppIsOther(false);
                    }
                  }}
                  disabled={categoriesLoading}
                  className="w-full appearance-none px-3 py-2 pr-8 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:text-gray-400"
                >
                  <option value="">{categoriesLoading ? "Loading categories…" : "Select a category…"}</option>
                  {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                {categoriesLoading
                  ? <Loader2 className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 animate-spin pointer-events-none" />
                  : <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
                }
              </div>
            )}

            {selectedCategory && apps.length > 0 && (
              <div className="relative">
                <select
                  value={selectedApp ? String(selectedApp.id) : ""}
                  onChange={(e) => setSelectedApp(apps.find((a) => String(a.id) === e.target.value) ?? null)}
                  className="w-full appearance-none px-3 py-2 pr-8 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Select an app (top 10)…</option>
                  {apps.map((a) => <option key={String(a.id)} value={String(a.id)}>{a.name}</option>)}
                </select>
                <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
            )}
          </div>

          <div className="flex justify-end">
            <button
              onClick={() => selectedApp && onAnalyzeStore(selectedApp, store, reviewCount)}
              disabled={!canSubmitStore}
              className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold disabled:opacity-40 hover:bg-indigo-700 transition-colors shadow-sm"
            >
              Fetch &amp; Analyze →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
