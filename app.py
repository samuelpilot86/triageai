"""
app.py — Chainlit interface for the TriageAI agent.
Deployed on HuggingFace Spaces (Docker, port 7860).
"""

import os
import chainlit as cl
import pandas as pd

from agent import FeedbackTriageAgent
from scraper import (
    APP_CATALOG,
    APP_TRIGGER_KEYWORDS,
    format_catalog_message,
    find_app,
    fetch_reviews,
)

# ------------------------------------------------------------------
# Visual mappings
# ------------------------------------------------------------------

PRIORITY_EMOJI = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}

CATEGORY_EMOJI = {
    "Bug / Error": "🐛",
    "Feature Request": "✨",
    "UX / Usability": "🎨",
    "Performance": "⚡",
    "Pricing": "💰",
    "Onboarding / Documentation": "📚",
    "Customer Support": "🎧",
    "Security / Privacy": "🔒",
    "Other": "📌",
}

# ------------------------------------------------------------------
# Welcome message
# ------------------------------------------------------------------

WELCOME_MESSAGE = """# 🎯 TriageAI — Product Feedback Triage Agent

Welcome! I'm your AI agent specialized in analyzing and prioritizing user feedbacks.

---

### How to use this tool

**Option 1 — Paste your feedbacks**
Paste your user feedback directly in the chat, **one feedback per line**.

**Option 2 — Upload a CSV**
Import a `.csv` file with a `feedback` column (or the first column will be used automatically).

**Option 3 — App Store / Google Play reviews** *(new!)*
Type `apps` to browse the catalog of 15 apps and automatically fetch their latest reviews.

> 💡 A `sample_feedbacks.csv` file is available in the repo to test immediately.

---

### What I do automatically

- 🏷️ **Categorizes** each feedback (Bug, Feature Request, UX, Performance…)
- 🔥 **Prioritizes** with justification (High / Medium / Low)
- 😊 **Analyzes sentiment** (Positive / Neutral / Negative)
- 🔍 **Self-corrects** — reviews its own decisions and revises them if needed
- 🔄 **Auto-fallback** — switches to Llama 3.3 70B (Groq) if Gemini quota is reached
- 📊 **Generates an executive report** with Top 3 recommendations
- 💾 **CSV export** of results available for download

---

*Paste your feedbacks, upload a CSV, or type `apps` to get started!*
"""

# ------------------------------------------------------------------
# Session initialization
# ------------------------------------------------------------------


@cl.on_chat_start
async def on_chat_start():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        await cl.Message(
            content=(
                "⚠️ **Missing configuration**\n\n"
                "The `GEMINI_API_KEY` environment variable is not set.\n\n"
                "**On HuggingFace Spaces:** go to *Settings → Repository secrets* "
                "and add `GEMINI_API_KEY` with your Google AI Studio key.\n\n"
                "Get a free key at [aistudio.google.com](https://aistudio.google.com/app/apikey)."
            )
        ).send()
        return

    groq_api_key = os.environ.get("GROQ_API_KEY")
    agent = FeedbackTriageAgent(api_key=api_key, groq_api_key=groq_api_key)
    cl.user_session.set("agent", agent)
    cl.user_session.set("mode", None)

    await cl.Message(content=WELCOME_MESSAGE).send()


# ------------------------------------------------------------------
# Main pipeline (shared across all 3 input modes)
# ------------------------------------------------------------------


async def _run_pipeline(feedbacks: list[str], agent: FeedbackTriageAgent) -> None:
    """Runs the 3-step agent pipeline on a list of feedbacks."""

    # Step 1 — Reading
    step1 = cl.Step(name="📥 Loading feedbacks", type="tool")
    step1.input = f"{len(feedbacks)} feedbacks received."
    step1.output = f"**{len(feedbacks)} feedbacks** received and ready for analysis."
    await step1.send()

    # Step 2 — Categorization & Self-validation (single LLM call)
    items: list[dict] = []
    corrections: list[dict] = []
    categorization_error = None
    step2 = cl.Step(name="🏷️ Categorization, Prioritization & Self-validation", type="llm")
    step2.input = f"Analyzing + self-correcting {len(feedbacks)} feedbacks with Gemini…"
    step2.output = "⏳ In progress…"
    await step2.send()
    used_fallback = False
    try:
        items, corrections, used_fallback = await agent.categorize_and_validate(feedbacks)
        lines = [f"✅ {len(items)} feedbacks categorized and validated."]
        if used_fallback:
            lines.append(
                f"⚠️ *Gemini quota reached — analysis performed by **Llama 3.3 70B** (Groq). "
                f"Results may vary slightly.*"
            )
        if corrections:
            lines.append(f"🔍 **{len(corrections)} auto-correction(s) applied:**")
            for c in corrections:
                field_label = {
                    "category": "category",
                    "priority": "priority",
                    "sentiment": "sentiment",
                }.get(c.get("field", ""), c.get("field", ""))
                lines.append(
                    f"- Feedback #{c.get('id')} — {field_label}: "
                    f"`{c.get('old_value')}` → **{c.get('new_value')}** "
                    f"*({c.get('reason', '')})*"
                )
        else:
            lines.append("🔍 No corrections needed.")
        step2.output = "\n".join(lines)
    except Exception as e:
        categorization_error = str(e)
        step2.output = f"❌ Error: {categorization_error}"
    await step2.update()

    if categorization_error:
        await cl.Message(
            content=f"❌ **Categorization error**\n\n`{categorization_error}`"
        ).send()
        return

    # Step 3 — Executive report
    report = ""
    report_error = None
    step4 = cl.Step(name="📊 Generating executive report", type="llm")
    step4.input = "Writing PM report…"
    step4.output = "⏳ In progress…"
    await step4.send()
    try:
        report, report_fallback = await agent.generate_report(items)
        note = (
            " *(Llama 3.3 70B — Groq fallback)*" if report_fallback else ""
        )
        step4.output = f"✅ Report generated.{note}"
    except Exception as e:
        report_error = str(e)
        step4.output = f"❌ Report error: {report_error}"
    await step4.update()

    # Detailed results table
    if items:
        rows = [
            "| # | Summary | Category | Priority | Reason | Sentiment |",
            "|---|---------|----------|----------|--------|-----------|",
        ]
        for item in items:
            cat = item.get("category", "Other")
            prio = item.get("priority", "Medium")
            rows.append(
                f"| {item.get('id', '')} "
                f"| {item.get('summary', '')[:55]} "
                f"| {CATEGORY_EMOJI.get(cat, '📌')} {cat} "
                f"| {PRIORITY_EMOJI.get(prio, '🟡')} {prio} "
                f"| {item.get('priority_reason', '')} "
                f"| {item.get('sentiment', '')} |"
            )
        await cl.Message(
            content="## 📋 Detailed Results\n\n" + "\n".join(rows)
        ).send()

    # Statistics
    if items:
        df_r = pd.DataFrame(items)
        cat_counts = df_r["category"].value_counts()
        prio_counts = df_r["priority"].value_counts()
        sent_counts = df_r["sentiment"].value_counts()

        stats = ["### 📈 Statistics\n"]
        stats.append("**By category:**")
        for cat, count in cat_counts.items():
            pct = round(count / len(items) * 100)
            stats.append(
                f"- {CATEGORY_EMOJI.get(cat, '📌')} {cat} — **{count}** ({pct}%)"
            )
        stats.append("\n**By priority:**")
        for prio, count in prio_counts.items():
            stats.append(f"- {PRIORITY_EMOJI.get(prio, '🟡')} {prio} — **{count}**")
        stats.append("\n**By sentiment:**")
        for sent, count in sent_counts.items():
            emoji = "😊" if sent == "Positive" else ("😐" if sent == "Neutral" else "😞")
            stats.append(f"- {emoji} {sent} — **{count}**")

        await cl.Message(content="\n".join(stats)).send()

    # Executive report
    if report:
        await cl.Message(content=f"## 🎯 Executive Report\n\n{report}").send()

    # CSV export
    if items:
        df_export = pd.DataFrame(items)
        tmp_path = "/tmp/triageai_results.csv"
        df_export.to_csv(tmp_path, index=False, encoding="utf-8-sig")
        elements = [
            cl.File(
                name="triageai_results.csv",
                path=tmp_path,
                display="inline",
                mime="text/csv",
            )
        ]
        await cl.Message(content="💾 **CSV export ready:**", elements=elements).send()

    await cl.Message(
        content="✅ **Analysis complete!** Send new feedbacks to run another analysis."
    ).send()


# ------------------------------------------------------------------
# Message handling
# ------------------------------------------------------------------


@cl.on_message
async def on_message(message: cl.Message):
    agent: FeedbackTriageAgent | None = cl.user_session.get("agent")

    if not agent:
        await cl.Message(
            content="⚠️ Session expired or missing API key. Please reload the page."
        ).send()
        return

    content = message.content.strip()
    content_lower = content.lower()

    # ------------------------------------------------------------------
    # Mode 3 — App Store / Google Play
    # ------------------------------------------------------------------

    # Trigger: user wants to browse the catalog
    if not message.elements and content_lower in APP_TRIGGER_KEYWORDS:
        await cl.Message(content=format_catalog_message()).send()
        cl.user_session.set("mode", "app_selection")
        return

    # App selection from catalog
    if cl.user_session.get("mode") == "app_selection" and not message.elements:
        app = find_app(content)

        if not app:
            await cl.Message(
                content=(
                    f"❌ App not found: `{content}`\n\n"
                    f"Type a number between **1** and **{len(APP_CATALOG)}** "
                    f"or an app name (e.g. `calm`, `fitbit`).\n\n"
                    f"Type `apps` to see the list again."
                )
            ).send()
            return

        cl.user_session.set("mode", None)

        feedbacks: list[str] = []
        source = ""
        step_scrape = cl.Step(name=f"🌐 Fetching reviews — {app['name']}", type="tool")
        step_scrape.input = f"Scraping {app['name']} ({app['category']})…"
        step_scrape.output = "⏳ In progress…"
        await step_scrape.send()
        try:
            feedbacks, source = await fetch_reviews(app, count=50)
            if feedbacks:
                step_scrape.output = (
                    f"✅ **{len(feedbacks)} reviews fetched** from **{source}**."
                )
            else:
                step_scrape.output = "❌ No reviews fetched (all sources unavailable)."
        except Exception as e:
            step_scrape.output = f"❌ Error: {str(e)}"
        await step_scrape.update()

        if not feedbacks:
            await cl.Message(
                content=(
                    f"❌ **Could not fetch reviews for {app['name']}**\n\n"
                    "Both Google Play and App Store are unavailable for this app.\n\n"
                    "Try another app or paste your feedbacks manually."
                )
            ).send()
            return

        await cl.Message(
            content=(
                f"✅ **{len(feedbacks)} reviews fetched** from **{source}** "
                f"for **{app['name']}** ({app['category']})\n\n"
                f"Starting analysis…"
            )
        ).send()

        if len(feedbacks) > 50:
            feedbacks = feedbacks[:50]

        await _run_pipeline(feedbacks, agent)
        return

    # ------------------------------------------------------------------
    # Mode 1 & 2 — Uploaded CSV or pasted text
    # ------------------------------------------------------------------

    cl.user_session.set("mode", None)

    feedbacks: list[str] = []

    # --- Read uploaded CSV ---
    if message.elements:
        for element in message.elements:
            if element.name.lower().endswith(".csv"):
                try:
                    df_input = pd.read_csv(element.path)

                    feedback_col = df_input.columns[0]
                    for col in df_input.columns:
                        if any(
                            kw in col.lower()
                            for kw in [
                                "feedback", "comment", "review",
                                "avis", "texte", "text",
                            ]
                        ):
                            feedback_col = col
                            break

                    feedbacks = (
                        df_input[feedback_col]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .tolist()
                    )
                    feedbacks = [f for f in feedbacks if f and f != "nan"]

                    await cl.Message(
                        content=(
                            f"✅ **CSV imported successfully**\n\n"
                            f"- File: `{element.name}`\n"
                            f"- Column used: `{feedback_col}`\n"
                            f"- Feedbacks detected: **{len(feedbacks)}**"
                        )
                    ).send()

                except Exception as e:
                    await cl.Message(
                        content=f"❌ **Error reading CSV**\n\n`{str(e)}`"
                    ).send()
                    return

    # --- Read pasted text ---
    if not feedbacks and content:
        lines = [line.strip() for line in content.split("\n") if line.strip()]

        if len(lines) < 2:
            await cl.Message(
                content=(
                    "💡 Please enter **at least 2 feedbacks**, one per line — "
                    "or type `apps` to fetch reviews from the App Store / Google Play.\n\n"
                    "Example:\n"
                    "```\n"
                    "The app crashes on startup on iOS\n"
                    "Dark mode is missing, it's straining at night\n"
                    "Loading time is way too slow\n"
                    "```"
                )
            ).send()
            return

        feedbacks = lines

    if not feedbacks:
        await cl.Message(
            content=(
                "💡 Paste your feedbacks (one per line), upload a CSV, "
                "or type `apps` to fetch reviews automatically."
            )
        ).send()
        return

    if len(feedbacks) > 50:
        await cl.Message(
            content=(
                f"⚠️ **Limit applied**: the **first 50 feedbacks** out of {len(feedbacks)} "
                f"will be analyzed (free tier limit)."
            )
        ).send()
        feedbacks = feedbacks[:50]

    await _run_pipeline(feedbacks, agent)
