"""
agent.py — Core logic of the product feedback triage agent.
Uses Google Gemini 2.5 Flash as primary model, with Groq (Llama 3.3 70B)
as automatic fallback when the Gemini free-tier quota is exhausted.
"""

import json
import re
import pandas as pd
from google import genai
from groq import AsyncGroq


CATEGORIES = [
    "Bug / Error",
    "Feature Request",
    "UX / Usability",
    "Performance",
    "Pricing",
    "Onboarding / Documentation",
    "Customer Support",
    "Security / Privacy",
    "Other",
]

PRIMARY_MODEL = "gemini-2.5-flash-lite"
FALLBACK_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL_MAX_TOKENS = 32_768  # llama-3.3-70b-versatile hard limit

# Output token budget per feedback (JSON fields: original, summary, category,
# priority, priority_reason, sentiment + corrections) + fixed overhead
_TOKENS_PER_FEEDBACK = 250
_TOKENS_OVERHEAD = 512


class FeedbackTriageAgent:
    """
    Product feedback triage agent powered by Gemini 2.5 Flash.
    Automatically falls back to Groq (Llama 3.3 70B) on quota exhaustion.
    """

    def __init__(self, api_key: str, groq_api_key: str | None = None):
        self.client = genai.Client(api_key=api_key)
        self.groq_client = AsyncGroq(api_key=groq_api_key) if groq_api_key else None

    # ------------------------------------------------------------------
    # Central LLM call with fallback
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str, n_feedbacks: int | None = None, max_tokens: int | None = None) -> tuple[str, bool]:
        """
        Calls the primary model (Gemini). If quota is exhausted (429),
        falls back to Groq automatically.
        Returns (response_text, used_fallback).
        Raises if both models fail or Groq is not configured.
        """
        # Try Gemini first
        try:
            response = await self.client.aio.models.generate_content(
                model=PRIMARY_MODEL,
                contents=prompt,
            )
            return self._extract_text(response), False

        except Exception as e:
            error_str = str(e)
            is_quota = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

            if not is_quota:
                raise  # Non-quota error: propagate immediately

            # Quota exhausted — try Groq fallback
            if not self.groq_client:
                raise RuntimeError(
                    "Gemini quota exhausted and no GROQ_API_KEY configured. "
                    "Please set GROQ_API_KEY in your Space secrets to enable fallback."
                ) from e

            if max_tokens is None:
                n = n_feedbacks or 50
                max_tokens = min(
                    FALLBACK_MODEL_MAX_TOKENS,
                    _TOKENS_OVERHEAD + n * _TOKENS_PER_FEEDBACK,
                )
            response = await self.groq_client.chat.completions.create(
                model=FALLBACK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content, True

    # ------------------------------------------------------------------
    # Step 1: Categorization + Self-validation (single LLM call)
    # ------------------------------------------------------------------

    async def categorize_and_validate(
        self, feedbacks: list[str]
    ) -> tuple[list[dict], list[dict], bool]:
        """
        Categorizes feedbacks AND self-corrects in a single LLM call.
        Returns (final_items, corrections_list, used_fallback).
        """
        feedbacks_numbered = "\n".join(
            [f"{i + 1}. {f}" for i, f in enumerate(feedbacks)]
        )
        categories_str = ", ".join(CATEGORIES)

        prompt = f"""You are an expert product feedback analyst. Work in two phases.

FEEDBACKS TO ANALYZE:
{feedbacks_numbered}

═══ PHASE 1 — CATEGORIZATION ═══
For each feedback, determine:
- id          : item number (integer, starts at 1)
- original    : exact original text
- summary     : concise summary in 6 words or fewer
- category    : ONE of: {categories_str}
- priority    : "High", "Medium" or "Low"
  * High   = blocking issue or strong impact on retention/acquisition
  * Medium = significant friction but has a workaround
  * Low    = cosmetic improvement or edge case
- priority_reason : justification in 10 words or fewer
- sentiment   : "Positive", "Neutral" or "Negative"

═══ PHASE 2 — SELF-CORRECTION ═══
Review your own decisions critically:
- Is the category truly the most accurate one?
- Is the priority consistent with the real product impact?
- Does the sentiment accurately reflect the original text?
- Are there inconsistencies across similar feedbacks?
Apply corrections directly in the final feedbacks output.

Return ONLY valid JSON, no markdown, no surrounding text:
{{
  "feedbacks": [
    {{
      "id": 1,
      "original": "...",
      "summary": "...",
      "category": "...",
      "priority": "...",
      "priority_reason": "...",
      "sentiment": "..."
    }}
  ],
  "corrections": [
    {{
      "id": <corrected feedback id>,
      "field": "category" | "priority" | "sentiment",
      "old_value": "initial value",
      "new_value": "corrected value",
      "reason": "justification in 10 words max"
    }}
  ]
}}

If no corrections are needed, return "corrections": [].
Be selective: only flag genuinely justified corrections."""

        text, used_fallback = await self._call_llm(prompt, n_feedbacks=len(feedbacks))
        data = self._parse_json_response(text)
        return data.get("feedbacks", []), data.get("corrections", []), used_fallback

    # ------------------------------------------------------------------
    # Step 2: Executive report
    # ------------------------------------------------------------------

    async def generate_report(self, items: list[dict]) -> tuple[str, bool]:
        """
        Generates a PM executive report from the categorized feedbacks.
        Returns (report_text, used_fallback).
        """
        df = pd.DataFrame(items)

        category_stats = df["category"].value_counts().to_dict()
        priority_stats = df["priority"].value_counts().to_dict()
        sentiment_stats = df["sentiment"].value_counts().to_dict()

        # Group recurring issues by summary within each category, with frequency
        issue_clusters = []
        for cat, group in df[df["priority"].isin(["High", "Medium"])].groupby("category"):
            freq = group["summary"].value_counts()
            top_issues = [
                {"issue": issue, "count": int(count), "priority": "High" if any(
                    group[group["summary"] == issue]["priority"] == "High"
                ) else "Medium"}
                for issue, count in freq.head(4).items()
            ]
            issue_clusters.append({"category": cat, "total": len(group), "top_issues": top_issues})
        issue_clusters.sort(key=lambda x: x["total"], reverse=True)

        prompt = f"""You are a senior Product Manager. Generate an executive report based on this analysis of {len(items)} user feedbacks.

OVERVIEW:
- Sentiment: {json.dumps(sentiment_stats, ensure_ascii=False)}
- By priority: {json.dumps(priority_stats, ensure_ascii=False)}

ISSUE BREAKDOWN (High + Medium priority, grouped by theme):
{json.dumps(issue_clusters, ensure_ascii=False, indent=2)}

Generate the report using EXACTLY this markdown structure:

## Summary
[2-3 sentences on the overall product health, referencing the dominant issue themes specifically.]

## Top 3 Recommended Actions
1. **[Specific action targeting the most frequent issue]** — [Justification with numbers: how many users affected, expected impact]
2. **[Specific action targeting the 2nd issue cluster]** — [Justification with numbers]
3. **[Specific action targeting the 3rd issue cluster]** — [Justification with numbers]

## Weak Signal to Watch
[1 non-obvious insight — a low-frequency issue that could become critical, or an unexpected pattern in the data]

Rules:
- Name the actual issues (e.g. "fix filter search bug" not "fix bugs")
- Include counts/percentages to justify prioritization
- Each action must be specific enough to go directly into a sprint backlog
- Tone: senior product consultant, concise, decision-oriented"""

        # Report output is always short (~800-1200 tokens), regardless of input size
        text, used_fallback = await self._call_llm(prompt, max_tokens=2048)
        return text, used_fallback

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _extract_text(self, response) -> str:
        """Extracts text from the response, compatible with thinking models."""
        try:
            text = response.text
            if text:
                return text
        except (ValueError, AttributeError):
            pass
        try:
            parts = response.candidates[0].content.parts
            return "".join(
                p.text for p in parts
                if hasattr(p, "text") and p.text and not getattr(p, "thought", False)
            )
        except Exception:
            return ""

    def _parse_json_response(self, text: str) -> dict:
        """Cleans and parses the LLM JSON response. Handles truncated JSON."""
        if not text:
            return {}
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```", "", text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Response was likely truncated — attempt to recover the feedbacks array
            match = re.search(r'"feedbacks"\s*:\s*(\[.*)', text, re.DOTALL)
            if not match:
                raise
            array_text = match.group(1)
            # Find the last complete object (ending with })
            last_complete = array_text.rfind("},")
            if last_complete == -1:
                last_complete = array_text.rfind("}")
            if last_complete == -1:
                raise
            recovered = array_text[: last_complete + 1] + "]"
            feedbacks = json.loads(recovered)
            return {"feedbacks": feedbacks, "corrections": []}
