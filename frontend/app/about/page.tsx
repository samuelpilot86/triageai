"use client";

import { useState } from "react";
import Link from "next/link";
import AppFooter from "@/components/AppFooter";

// ── Data ────────────────────────────────────────────────────────────

const AGENTS = [
  {
    emoji: "🎯",
    name: "Sift",
    role: "Pre-filter",
    model: "Cerebras · gpt-oss-120b",
    desc: "Filters non-actionable reviews (spam, generic praise, off-topic)",
    modelClass: "cerebras",
  },
  {
    emoji: "🔬",
    name: "Iris",
    role: "Categorizer",
    model: "Gemini 3.1 Flash Lite",
    desc: "Classifies, prioritizes & self-corrects in a single structured call",
    modelClass: "gemini",
  },
  {
    emoji: "🗂️",
    name: "Echo",
    role: "Cluster Analyst",
    model: "Cerebras · gpt-oss-120b",
    desc: "LLM-driven semantic clustering — one cluster = one Jira ticket, scored by volume & severity",
    modelClass: "cerebras",
  },
  {
    emoji: "🖊️",
    name: "Penn",
    role: "Reporter",
    model: "Cerebras · Qwen 3 235B",
    desc: "Synthesizes top clusters into a PM executive report with prioritized recommendations",
    modelClass: "cerebras",
  },
  {
    emoji: "🃏",
    name: "Nova",
    role: "Backlog Builder",
    model: "Cerebras · Qwen 3 235B",
    desc: "Generates RICE-scored sprint cards with US and acceptance criteria, ready for Jira",
    modelClass: "cerebras",
  },
];

const MODEL_ROUTING = [
  {
    agent: "Sift",
    emoji: "🎯",
    badge: "Cerebras · gpt-oss-120b",
    badgeClass: "bg-orange-100 text-orange-800",
    why: "Single batched call on the full review set to discard non-actionable feedbacks. Cerebras' wafer-scale inference (~2100 tok/s) keeps this cheap step near-instant. This model is overkill for a binary filter — but we take advantage of its generous 1M tokens/day free quota.",
  },
  {
    agent: "Iris",
    emoji: "🔬",
    badge: "Gemini 3.1 Flash Lite",
    badgeClass: "bg-indigo-100 text-indigo-800",
    why: "The heaviest step: 4 parallel chunks of structured JSON classification with self-review. Gemini 3.1 Flash Lite's 500 RPD (vs 20 on 2.5) and 250K TPM absorb the per-run fan-out.",
  },
  {
    agent: "Echo",
    emoji: "🗂️",
    badge: "Cerebras · gpt-oss-120b",
    badgeClass: "bg-orange-100 text-orange-800",
    why: "LLM clustering over summaries — small, semantically rich input. gpt-oss-120b's reasoning is more than enough for coherent grouping, and Cerebras' 1M tokens/day headroom means clustering never becomes the bottleneck on repeated runs.",
  },
  {
    agent: "Penn",
    emoji: "🖊️",
    badge: "Cerebras · Qwen 3 235B",
    badgeClass: "bg-rose-100 text-rose-800",
    why: "Narrative synthesis for a stakeholder-facing report. Qwen 3 235B performs close to Opus 4 ; Cerebras serves it at ~2000 tok/s so a rich report still renders in seconds.",
  },
  {
    agent: "Nova",
    emoji: "🃏",
    badge: "Cerebras · Qwen 3 235B",
    badgeClass: "bg-rose-100 text-rose-800",
    why: "RICE scoring, user story format, acceptance criteria — requires PM domain understanding and structured output. Same reasoning muscle as Penn, same throughput budget, same free-tier pool.",
  },
];

const INTEGRATIONS = [
  {
    icon: "🍎",
    name: "App Store",
    type: "Input · iTunes Search API",
    typeClass: "text-indigo-600",
    desc: "Browse top apps by category or search by name.",
  },
  {
    icon: "▶️",
    name: "Google Play",
    type: "Input · google-play-scraper",
    typeClass: "text-indigo-600",
    desc: "Same workflow on Android.",
  },
  {
    icon: "📋",
    name: "Jira",
    type: "Output · REST API v3",
    typeClass: "text-emerald-600",
    desc: "One click pushes a sprint card directly to the team's board — Atlassian Document Format, issue type detection from action type.",
  },
];

const STACK_CATEGORIES = [
  {
    label: "Frontend",
    items: ["Next.js", "Vercel"],
  },
  {
    label: "Backend",
    items: ["FastAPI", "Server-Sent Events", "HuggingFace Spaces"],
  },
  {
    label: "AI Models",
    items: ["Cerebras · gpt-oss-120b", "Cerebras · Qwen 3 235B", "Gemini 3.1 Flash Lite"],
  },
  {
    label: "Integrations",
    items: ["Google Play API", "App Store API", "Jira REST API v3"],
  },
];

// ── Page ────────────────────────────────────────────────────────────

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-gray-50">

      {/* Nav — mirrors main page header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo.jpg" alt="trIAge logo" className="w-9 h-9 rounded-xl" />
            <div>
              <p className="text-lg font-semibold text-gray-900">trIAge</p>
              <p className="text-xs text-gray-400">Product feedback triage for PMs, powered by AI agents</p>
            </div>
          </div>
          <Link
            href="/"
            className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 border border-indigo-200 hover:border-indigo-400 hover:bg-indigo-50 px-3 py-1.5 rounded-lg transition-colors"
          >
            ⚡ Try the app
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-16 space-y-20">

        {/* ── Hero ── */}
        <section>
          <div className="inline-block bg-indigo-50 text-indigo-600 text-xs font-bold tracking-widest uppercase px-3 py-1 rounded-md mb-5">
            🔧 How it&apos;s built
          </div>
          <h1 className="text-3xl font-extrabold text-gray-900 leading-tight mb-4">
            An agentic AI pipeline,<br />from store reviews to your Jira backlog
          </h1>
          <p className="text-base text-gray-500 leading-relaxed max-w-xl">
            trIAge showcases Samuel&apos;s agentic AI prototyping skills. The goal: chain specialized agents, route tasks to the right models, and wire up real external systems end-to-end.
          </p>
          <p className="text-base text-gray-500 leading-relaxed max-w-xl mt-3">
            The result: a fast, zero-setup way to analyze any app&apos;s reviews — for your product or a competitor&apos;s — and draft sprint-ready backlog.
          </p>
        </section>

        {/* ── Architecture ── */}
        <section>
          <SectionLabel>Architecture</SectionLabel>
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Five specialized agents, one coordinated pipeline
          </h2>
          <p className="text-sm text-gray-500 mb-5 leading-relaxed">
            Each agent has a single responsibility, making it easy to spot errors and tune prompts.
            It also lays the groundwork for automated testing for scaling purposes.
          </p>

          {/* Pipeline flow with sources and Jira output */}
          <div className="flex items-center gap-0 bg-white rounded-2xl border border-gray-200 p-4">

            {/* Input sources — stacked vertically */}
            <div className="flex flex-col items-center gap-1.5 shrink-0">
              <SourcePill type="googleplay" />
              <SourcePill type="appstore" />
              <SourcePill type="csv" />
              <SourcePill type="text" />
            </div>

            {/* Connector: sources → Sift */}
            <PillConnector />

            {/* Agent cards */}
            <div className="flex items-stretch gap-0 flex-1 min-w-0">
              {AGENTS.map((a, i) => (
                <div key={a.name} className="flex items-center flex-1 min-w-0 gap-0">
                  <div className="flex-1 min-w-0 rounded-xl border border-gray-200 bg-gray-50 p-2.5">
                    <div className="text-lg mb-1">{a.emoji}</div>
                    <div className="text-xs font-bold text-gray-900">{a.name}</div>
                    <div className="text-[10px] font-semibold text-indigo-500 mb-1">{a.role}</div>
                    <div className={`text-[9px] font-mono mb-1.5 ${
                      a.modelClass === "cerebras" ? "text-orange-600" :
                      a.modelClass === "gemini" ? "text-indigo-500" : "text-gray-400"
                    }`}>{a.model}</div>
                    <div className="text-[10px] text-gray-500 leading-snug">{a.desc}</div>
                  </div>
                  {i < AGENTS.length - 1 && (
                    <AgentArrow />
                  )}
                </div>
              ))}
            </div>

            {/* Connector: Nova → Jira */}
            <PillConnector />

            {/* Jira output */}
            <JiraPill />
          </div>
        </section>

        {/* ── Model routing ── */}
        <section>
          <SectionLabel>Model routing</SectionLabel>
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Speed where it matters, quality where it shows
          </h2>
          <p className="text-sm text-gray-500 mb-2 leading-relaxed">
            Each step is routed to the provider whose model quality and capabilities, throughput and free-tier limits best match its workload.
          </p>
          <ul className="text-sm text-gray-500 mb-6 space-y-1 pl-4">
            <li className="list-disc leading-relaxed">Cerebras handles the heavy reasoning at wafer-scale speed.</li>
            <li className="list-disc leading-relaxed">Gemini absorbs the parallel fan-out of the categorization step.</li>
          </ul>

          <div className="rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left text-xs font-bold uppercase tracking-wider text-gray-400 px-4 py-3 w-24">Agent</th>
                  <th className="text-left text-xs font-bold uppercase tracking-wider text-gray-400 px-4 py-3 w-44">Model</th>
                  <th className="text-left text-xs font-bold uppercase tracking-wider text-gray-400 px-4 py-3">Why this choice</th>
                </tr>
              </thead>
              <tbody>
                {MODEL_ROUTING.map((row, i) => (
                  <tr key={row.agent} className={i < MODEL_ROUTING.length - 1 ? "border-b border-gray-100" : ""}>
                    <td className="px-4 py-3">
                      <div className="text-base leading-none mb-1">{row.emoji}</div>
                      <div className="font-semibold text-gray-900 text-sm">{row.agent}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-block text-xs font-mono font-semibold px-2 py-1 rounded-md ${row.badgeClass}`}>
                        {row.badge}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs leading-relaxed">{row.why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Self-correction ── */}
        <section>
          <SectionLabel>Precision</SectionLabel>
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Self-correcting classification — one call, two passes
          </h2>
          <p className="text-sm text-gray-500 mb-6 leading-relaxed">
            Iris achieves higher accuracy without a second model or a second API call. The prompt is structured
            in two explicit phases within a single request.
          </p>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <div className="text-xs font-bold uppercase tracking-wider text-indigo-500 mb-2">Phase 1 — Classify</div>
              <div className="text-sm font-semibold text-gray-900 mb-2">First pass</div>
              <p className="text-xs text-gray-500 leading-relaxed">
                For each feedback: assign category, priority (High / Medium / Low),
                sentiment, and an actionability flag that filters out noise with no product signal.
              </p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <div className="text-xs font-bold uppercase tracking-wider text-emerald-500 mb-2">Phase 2 — Self-review</div>
              <div className="text-sm font-semibold text-gray-900 mb-2">Critique & correct</div>
              <p className="text-xs text-gray-500 leading-relaxed">
                Iris reviews its own decisions — checks for inconsistencies across similar feedbacks,
                corrects mislabeled priorities or categories, and logs every change made.
              </p>
            </div>
          </div>

          <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-xs text-gray-600 leading-relaxed">
            <span className="font-semibold text-gray-900">Why it&apos;s efficient:</span>{" "}
            A second agent reviewing Iris&apos;s output would mean a second API call — and free-tier providers enforce
            limits on both tokens per minute and daily request count. Structuring the prompt in two explicit phases
            achieves similar precision in a single round-trip — a deliberate choice over naive agent chaining.
          </div>
        </section>

        {/* ── Integrations ── */}
        <section>
          <SectionLabel>Integrations</SectionLabel>
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Connected to where product data lives
          </h2>
          <p className="text-sm text-gray-500 mb-6 leading-relaxed">
            trIAge connects to two data sources and one delivery target. The pipeline runs from raw store reviews to a Jira ticket without leaving the interface.
          </p>

          <div className="grid grid-cols-3 gap-3">
            {INTEGRATIONS.map((integ) => (
              <div key={integ.name} className="rounded-xl border border-gray-200 bg-white p-4">
                <div className="text-2xl mb-3">{integ.icon}</div>
                <div className="text-sm font-bold text-gray-900 mb-0.5">{integ.name}</div>
                <div className={`text-[10px] font-semibold mb-3 ${integ.typeClass}`}>{integ.type}</div>
                <p className="text-xs text-gray-500 leading-relaxed">{integ.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Stack ── */}
        <section>
          <SectionLabel>Stack</SectionLabel>
          <h2 className="text-xl font-bold text-gray-900 mb-5">Built with</h2>
          <div className="space-y-4">
            {STACK_CATEGORIES.map((cat) => (
              <div key={cat.label} className="flex items-start gap-4">
                <span className="text-xs font-bold uppercase tracking-wider text-gray-400 w-24 shrink-0 pt-1.5">
                  {cat.label}
                </span>
                <div className="flex flex-wrap gap-2">
                  {cat.items.map((item) => (
                    <span
                      key={item}
                      className="text-xs font-mono text-gray-600 bg-gray-100 px-3 py-1.5 rounded-lg"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── About the maker ── */}
        <section>
          <SectionLabel>Maker</SectionLabel>
          <div className="rounded-2xl border border-gray-200 bg-white p-6 flex flex-col sm:flex-row items-start gap-6">
          jsx{/* Photo */}
            <div className="shrink-0">
              <img
                src="/samuel.jpg"
                alt="Samuel PILOT"
                className="w-24 h-auto rounded-2xl object-contain"
              />
            </div>

            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-bold text-gray-900 mb-1">Samuel PILOT</h3>
              <p className="text-sm text-gray-500 leading-relaxed mb-4">
                Product Manager and Builder with a Product Owner (BearingPoint) and engineering (Mines Paris) background.
                trIAge was designed as a concrete demonstration of agentic AI engineering applied to a real PM workflow.
              </p>
              <div className="flex items-center gap-3 flex-wrap mb-6">
                <a
                  href="https://linktr.ee/samuelpilot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold hover:bg-indigo-100 transition-colors"
                >
                  <LinktreeIcon />
                  Portfolio
                </a>
                <a
                  href="https://www.linkedin.com/in/samuelpilot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-50 border border-sky-200 text-sky-700 text-xs font-semibold hover:bg-sky-100 transition-colors"
                >
                  <LinkedInIcon />
                  LinkedIn
                </a>
              </div>

              {/* Contact form */}
              <ContactForm />
            </div>
          </div>
        </section>

        {/* ── CTA ── */}
        <section className="rounded-2xl bg-gradient-to-br from-indigo-50 to-emerald-50 border border-indigo-100 p-8 text-center">
          <h3 className="text-lg font-bold text-gray-900 mb-2">See it in action</h3>
          <p className="text-sm text-gray-500 mb-6 max-w-sm mx-auto">
            Run a live analysis on any app from the App Store or Google Play.
            Results in under 60 seconds — no account, no setup.
          </p>
          <Link
            href="/"
            className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-6 py-2.5 rounded-lg transition-colors"
          >
            Try trIAge →
          </Link>
        </section>

      </main>

      <AppFooter />
    </div>
  );
}

// ── Pipeline icons (same as AgentPipeline.tsx) ───────────────────────

function GooglePlayIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" xmlns="http://www.w3.org/2000/svg">
      <path d="M1.22 0c-.338.196-.22.618-.22 1.03v21.94c0 .414-.118.834.22 1.03l.08.06 12.28-12.26v-.3L1.3-.06l-.08.06z" fill="#4285F4"/>
      <path d="M17.68 16.49l-4.09-4.1v-.3l4.09-4.09.09.05 4.84 2.75c1.38.78 1.38 2.06 0 2.84l-4.84 2.75-.09.05z" fill="#FBBC04"/>
      <path d="M17.77 16.44L13.5 12 1.22 24.26c.456.484 1.207.544 1.74.14l14.81-7.96" fill="#EA4335"/>
      <path d="M17.77 7.56L2.96.74C2.427.336 1.676.396 1.22.88L13.5 12l4.27-4.44z" fill="#34A853"/>
    </svg>
  );
}

function AppStoreIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" xmlns="http://www.w3.org/2000/svg">
      <rect width="24" height="24" rx="5.5" fill="#0D96F6"/>
      {/* Stylized App Store "A" — two crossed lines forming a tent shape with a crossbar */}
      <g fill="white">
        <path d="M12 4.5l-4.5 8h2.1l.9-1.7h3l.9 1.7h2.1L12 4.5zm0 2.8l1.05 2.2h-2.1L12 7.3z"/>
        <path d="M6.5 13.5h11v1.5h-11z"/>
        <path d="M8 15.5l-1.5 3h1.8l.4-.9h6.6l.4.9h1.8l-1.5-3H8zm2 1.5h4l-.5 1.1h-3L10 17z"/>
      </g>
    </svg>
  );
}

function CsvIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#6b7280" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
    </svg>
  );
}

function TextIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#6b7280" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
    </svg>
  );
}

function JiraIconSvg() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" xmlns="http://www.w3.org/2000/svg" fill="white">
      <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.004-1.005zm5.723-5.756H5.757a5.215 5.215 0 0 0 5.214 5.214h2.132v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.024-1.001zM23.013 0H11.476a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.49V1.005A1.001 1.001 0 0 0 23.013 0z"/>
    </svg>
  );
}

function SourcePill({ type }: { type: "googleplay" | "appstore" | "csv" | "text" }) {
  const base = "w-8 h-8 rounded-full flex items-center justify-center shrink-0 border bg-white border-gray-200 shadow-sm";
  const labels: Record<string, string> = {
    googleplay: "Google Play",
    appstore: "App Store",
    csv: "CSV",
    text: "Paste / Demo",
  };
  return (
    <div className={base} title={labels[type]}>
      {type === "googleplay" && <GooglePlayIcon />}
      {type === "appstore" && <AppStoreIcon />}
      {type === "csv" && <CsvIcon />}
      {type === "text" && <TextIcon />}
    </div>
  );
}

function JiraPill() {
  return (
    <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-[#0052CC] shadow-sm" title="Jira">
      <JiraIconSvg />
    </div>
  );
}

function PillConnector() {
  return <div className="w-3 h-0.5 bg-gray-200 shrink-0" />;
}

function AgentArrow() {
  return (
    <div className="shrink-0 flex items-center justify-center px-0.5 text-gray-300">
      <svg width="16" height="10" viewBox="0 0 20 12" fill="none">
        <path d="M0 6h16M12 1l6 5-6 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// ── Social icons ────────────────────────────────────────────────────

function LinktreeIcon({ size = 14 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="m13.73635 5.85251 4.00467-4.11665 2.3248 2.3808-4.20064 4.00466h5.9085v3.30473h-5.9365l4.22865 4.10766-2.3248 2.3338L12.0005 12.099l-5.74052 5.76852-2.3248-2.3248 4.22864-4.10766h-5.9375V8.12132h5.9085L3.93417 4.11666l2.3248-2.3808 4.00468 4.11665V0h3.4727zm-3.4727 10.30614h3.4727V24h-3.4727z"/>
    </svg>
  );
}

function LinkedInIcon({ size = 14 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
    </svg>
  );
}

// ── Contact form ─────────────────────────────────────────────────────

function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("sending");
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, message }),
      });
      if (!res.ok) throw new Error();
      setStatus("sent");
      setName(""); setEmail(""); setMessage("");
    } catch {
      setStatus("error");
    }
  }

  if (status === "sent") {
    return (
      <div className="rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700 font-medium">
        ✓ Message sent — I&apos;ll get back to you shortly.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Send a message</p>
      <div className="grid grid-cols-2 gap-3">
        <input
          type="text"
          placeholder="Your name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-400 placeholder:text-gray-400"
        />
        <input
          type="email"
          placeholder="Your email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-400 placeholder:text-gray-400"
        />
      </div>
      <textarea
        placeholder="Your message"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        required
        rows={3}
        className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-400 placeholder:text-gray-400 resize-none"
      />
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={status === "sending"}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold transition-colors"
        >
          {status === "sending" ? "Sending…" : "Send →"}
        </button>
        {status === "error" && (
          <span className="text-xs text-red-500">Something went wrong — try again.</span>
        )}
      </div>
    </form>
  );
}

// ── Helper ──────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-2">
      {children}
    </p>
  );
}
