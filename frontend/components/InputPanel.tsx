"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Upload, ChevronDown, ClipboardList, FileSpreadsheet, Star, Zap } from "lucide-react";
import { Store, AppEntry } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

type Tab = "text" | "csv" | "store" | "demo";

interface Props {
  onAnalyzeText: (feedbacks: string[]) => void;
  onAnalyzeCsv: (file: File) => void;
  onAnalyzeStore: (app: AppEntry, store: Store) => void;
  disabled?: boolean;
}

const SAMPLE_FEEDBACKS = `The app crashes every time I try to open it after the latest update
Dark mode is missing and my eyes hurt using it at night
Loading times are way too slow, sometimes takes 10+ seconds
Love the new dashboard design, it's so much cleaner
Notifications keep showing up even after I disabled them
The search bar doesn't work properly, results are always wrong
Please add a widget for the home screen, would be super useful
Can't export my data to PDF, the button does nothing
The app randomly logs me out every few hours, very frustrating
Great app overall but the onboarding is confusing for new users
The premium plan is way too expensive for what it offers
Fingerprint login stopped working after iOS 17 update
I love how fast the sync is between devices, excellent feature
Charts are impossible to read on small screens
Would love a collaborative mode to share projects with teammates
The undo button doesn't always work, lost my work twice
Battery drain is insane, kills 30% in an hour just running in background
Excellent customer support, they solved my issue in minutes
The calendar integration with Google is broken since last week
Font size is too small and there's no way to change it
Please add offline mode, useless without internet
The free tier is too limited, only 5 items is ridiculous
App froze completely during a presentation, very embarrassing
Love the autosave feature, saved me from losing work many times
Tags and filters are confusing, took me a week to understand
Why does the app need access to my contacts and microphone?
The AI suggestions are surprisingly accurate and helpful
Sync fails silently — no error message, data just disappears
The iPad layout is terrible, everything looks stretched
Please add keyboard shortcuts for power users
I switched from the competitor and this is significantly better
The color themes are beautiful but I want to create custom ones
Payment failed but I was still charged, need a refund
The map feature is laggy and the pins load slowly
Love the weekly summary emails, very motivating
The tutorial skips too fast and can't be replayed
Push notifications arrive 30 minutes late, completely useless
Onboarding walkthrough was clear and well designed
The widget crashes the home screen on Android 13
CSV import doesn't handle special characters like é or ü
Can you add a passcode lock for privacy?
The graph animations are smooth and really polished
Autocomplete suggestions are often irrelevant and annoying
Storage limit reached with no warning, lost unsaved data
The new update broke the dark mode completely
I'd pay more for a family plan option
App size is 800MB which is absurd for what it does
The voice input feature is a game changer, love it
Recurring tasks don't reset correctly after completion
The help documentation is outdated and missing many features
App took 3 minutes to load this morning, something is wrong
Love the Siri shortcut integration, works perfectly
The sharing feature posts to wrong account sometimes
Streak tracking is super motivating, great addition
Can't attach files larger than 5MB, this limit is too low
The desktop web version is much better than the mobile app
Login with Apple doesn't work, always shows an error
The monthly report is beautiful and very actionable
Need a batch delete option, deleting one by one is painful
The map doesn't show my current location accurately
Excellent app, I recommend it to all my colleagues
The color contrast is poor, hard to read for colorblind users
Crashes on Android 12 every time I use the camera feature
The price increase from $5 to $12 is not justified
Real-time collaboration works flawlessly, impressive engineering
The search doesn't find items by tags, only by title
Would love an Apple Watch companion app
The loading spinner shows forever on slow connections
I lost all my data after reinstalling the app, no backup warning
The haptic feedback is satisfying and well-tuned
Two-factor authentication setup is overly complicated
The API integration with Zapier is broken since v3.2
Simple and intuitive, my whole team adopted it in one day
The free trial is too short — 3 days is not enough to evaluate
Background refresh drains battery extremely fast
The drag and drop reordering is smooth and responsive
Please add a trash/recycle bin before deleting permanently
The app grammar checker is excellent, catches subtle errors
Analytics dashboard doesn't load on Firefox
Can't cancel my subscription from within the app, must use website
The new icon is ugly, please bring back the old one
Reminders don't fire when the phone is on silent mode
The recent redesign is gorgeous and feels premium
Import from Notion is broken, files come in with wrong formatting
Sorting options are too limited, need more criteria
The app doesn't remember my scroll position when switching tabs
Love the community feature, met many useful connections
The mandatory account creation to try the app is a dealbreaker
Response time from in-app chat support is under 5 minutes, wow
The location-based reminders work perfectly, very reliable
Duplicating a project copies everything except the attachments
Need a proper Windows desktop app, the web version is not enough
The AI writing assistant suggestions are hit or miss
Switching between accounts is clunky and takes too many taps
The image compression ruins quality, photos look pixelated
Absolutely the best app in this category, nothing comes close
The monthly price went up but no new features were added
Graph data export to Excel doesn't preserve formatting
The accessibility features for VoiceOver users are exemplary`;

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
  const [dragOver, setDragOver] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [store, setStore] = useState<Store>("googleplay");
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
            readOnly
            value={SAMPLE_FEEDBACKS}
            className="w-full h-52 px-4 py-3 text-sm rounded-xl border border-gray-200 bg-gray-50 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-500"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">100 sample feedbacks</span>
            <button
              onClick={() => onAnalyzeText(SAMPLE_FEEDBACKS.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 100))}
              disabled={disabled}
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
          {/* Store toggle */}
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
