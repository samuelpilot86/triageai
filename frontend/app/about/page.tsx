import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";

export const metadata: Metadata = {
  title: "trIAge — How it's built",
  description:
    "Architecture, model routing, and integration decisions behind trIAge.",
};

// ── Data ────────────────────────────────────────────────────────────

const AGENTS = [
  {
    emoji: "🕸️",
    name: "Webb",
    role: "Web Scraper",
    model: "Python scraper",
    desc: "Fetches live reviews from App Store & Google Play via public APIs",
    modelClass: "python",
  },
  {
    emoji: "🔬",
    name: "Iris",
    role: "Categorizer",
    model: "Groq · Llama 3.3 70B",
    desc: "Classifies, prioritizes & self-corrects in a single structured call",
    modelClass: "groq",
  },
  {
    emoji: "🖊️",
    name: "Penn",
    role: "Reporter",
    model: "Gemini 2.5 Flash",
    desc: "Synthesizes findings into a PM executive report",
    modelClass: "gemini",
  },
  {
    emoji: "✨",
    name: "Nova",
    role: "Backlog Builder",
    model: "Gemini 2.5 Flash",
    desc: "Generates RICE-scored sprint cards, ready for Jira",
    modelClass: "gemini",
  },
];

const MODEL_ROUTING = [
  {
    agent: "Webb",
    badge: "Python",
    badgeClass: "bg-slate-100 text-slate-600",
    why: "Pure data fetching — no LLM needed. Scraping App Store & Google Play APIs directly.",
  },
  {
    agent: "Iris",
    badge: "Groq · Llama 3.3 70B",
    badgeClass: "bg-amber-100 text-amber-800",
    why: "Structured JSON classification — speed matters, creativity doesn't. Groq's inference hardware makes this step visibly faster, and its free tier is generous enough for batch processing.",
  },
  {
    agent: "Penn",
    badge: "Gemini 2.5 Flash",
    badgeClass: "bg-indigo-100 text-indigo-800",
    why: "Narrative synthesis for a stakeholder-facing report. Language quality is directly visible to the end user — best available free-tier model for this task.",
  },
  {
    agent: "Nova",
    badge: "Gemini 2.5 Flash",
    badgeClass: "bg-indigo-100 text-indigo-800",
    why: "RICE scoring, user story format, acceptance criteria — requires PM domain understanding and structured output. Gemini Flash handles both well.",
  },
];

const INTEGRATIONS = [
  {
    icon: "🍎",
    name: "App Store",
    type: "Input · iTunes Search API",
    typeClass: "text-indigo-600",
    desc: "Browse top apps by category or search by name. Fetches up to 50 reviews (Apple RSS feed hard limit).",
  },
  {
    icon: "▶️",
    name: "Google Play",
    type: "Input · google-play-scraper",
    typeClass: "text-indigo-600",
    desc: "Same workflow on Android. Category browsing, app search by name, live review fetch.",
  },
  {
    icon: "📋",
    name: "Jira",
    type: "Output · REST API v3",
    typeClass: "text-emerald-600",
    desc: "One click pushes a sprint card directly to the team's board — Atlassian Document Format, priority mapping, issue type detection from action type.",
  },
];

const STACK = [
  "Next.js", "FastAPI", "Server-Sent Events",
  "Gemini 2.5 Flash", "Groq · Llama 3.3 70B",
  "Google Play API", "App Store API", "Jira REST API v3",
  "Vercel", "HuggingFace Spaces",
];

// ── Page ────────────────────────────────────────────────────────────

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-white">

      {/* Nav */}
      <nav className="border-b border-gray-100">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <Image src="/logo.jpg" alt="trIAge" width={28} height={28} className="rounded-lg" />
            <span className="text-sm font-semibold text-gray-900">trIAge</span>
          </Link>
          <Link
            href="/"
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
          >
            Try the app →
          </Link>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-16 space-y-20">

        {/* ── Hero ── */}
        <section>
          <div className="inline-block bg-indigo-50 text-indigo-600 text-xs font-bold tracking-widest uppercase px-3 py-1 rounded-md mb-5">
            🔧 How it&apos;s built
          </div>
          <h1 className="text-3xl font-extrabold text-gray-900 leading-tight mb-4">
            An agentic AI pipeline,<br />connected to real systems
          </h1>
          <p className="text-base text-gray-500 leading-relaxed max-w-xl">
            trIAge was built to demonstrate what agentic AI engineering looks like in a concrete product context —
            not to validate a market opportunity. The goal: chain specialized agents, route tasks to the right
            models, and wire up real external systems end-to-end.
          </p>
          <p className="text-base text-gray-500 leading-relaxed max-w-xl mt-3">
            The result turns out to be practically useful too: a fast, zero-setup way to turn any app's reviews
            into a structured analysis and a sprint-ready backlog — for your own product or a competitor's.
          </p>
        </section>

        {/* ── Architecture ── */}
        <section>
          <SectionLabel>Architecture</SectionLabel>
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Four specialized agents, one coordinated pipeline
          </h2>
          <p className="text-sm text-gray-500 mb-3 leading-relaxed">
            Each agent has a single, well-defined responsibility.
            Because each step produces a discrete, inspectable output, it's straightforward to observe what
            each agent actually did — useful for spotting errors, tuning prompts, or understanding failure modes.
            It also lays the groundwork for automated testing: each step can be validated independently,
            with assertions on the output format and content before the next agent is triggered.
          </p>

          {/* Agent cards */}
          <div className="flex items-stretch gap-2 mb-4">
            {AGENTS.map((a, i) => (
              <div key={a.name} className="flex items-center flex-1 min-w-0 gap-2">
                <div className="flex-1 min-w-0 rounded-xl border border-gray-200 bg-gray-50 p-3">
                  <div className="text-xl mb-2">{a.emoji}</div>
                  <div className="text-xs font-bold text-gray-900">{a.name}</div>
                  <div className="text-[10px] font-semibold text-indigo-500 mb-1">{a.role}</div>
                  <div className={`text-[9px] font-mono mb-2 ${
                    a.modelClass === "groq" ? "text-amber-700" :
                    a.modelClass === "gemini" ? "text-indigo-500" : "text-gray-400"
                  }`}>{a.model}</div>
                  <div className="text-[10px] text-gray-500 leading-snug">{a.desc}</div>
                </div>
                {i < AGENTS.length - 1 && (
                  <span className="shrink-0 text-gray-300 text-sm">→</span>
                )}
              </div>
            ))}
          </div>

          <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-sm text-emerald-800 leading-relaxed">
            Results stream to the UI in real time via{" "}
            <span className="font-semibold">Server-Sent Events</span> — each
            agent's output appears as soon as it's ready, without waiting for the full pipeline to complete.
            Every step is visible: you watch the agents work rather than staring at a spinner.
          </div>
        </section>

        {/* ── Model routing ── */}
        <section>
          <SectionLabel>Model routing</SectionLabel>
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            The right model for the right task
          </h2>
          <p className="text-sm text-gray-500 mb-6 leading-relaxed">
            Using a single model for every step is the path of least resistance. Routing by task type is a
            deliberate choice: it reduces latency where speed matters, and preserves quality where the output
            is directly visible to the end user.
          </p>

          <div className="rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left text-xs font-bold uppercase tracking-wider text-gray-400 px-4 py-3 w-20">Agent</th>
                  <th className="text-left text-xs font-bold uppercase tracking-wider text-gray-400 px-4 py-3 w-44">Model</th>
                  <th className="text-left text-xs font-bold uppercase tracking-wider text-gray-400 px-4 py-3">Why this choice</th>
                </tr>
              </thead>
              <tbody>
                {MODEL_ROUTING.map((row, i) => (
                  <tr key={row.agent} className={i < MODEL_ROUTING.length - 1 ? "border-b border-gray-100" : ""}>
                    <td className="px-4 py-3 font-semibold text-gray-900">{row.agent}</td>
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
            <span className="font-semibold text-gray-900">Why it's efficient:</span>{" "}
            A second agent reviewing Iris's output would mean a second API call — and Groq's free tier
            enforces limits on both tokens per minute and number of requests. Structuring the prompt in two
            explicit phases achieves similar precision in a single round-trip — a deliberate choice over
            naive agent chaining.
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
            The pipeline runs from raw store reviews to a Jira ticket without leaving the interface.
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
          <h2 className="text-xl font-bold text-gray-900 mb-4">Built with</h2>
          <div className="flex flex-wrap gap-2">
            {STACK.map((item) => (
              <span
                key={item}
                className="text-xs font-mono text-gray-600 bg-gray-100 px-3 py-1.5 rounded-lg"
              >
                {item}
              </span>
            ))}
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
    </div>
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
