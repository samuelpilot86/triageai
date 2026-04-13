"""
agent.py — Core logic of the product feedback triage agent.
Uses Google Gemini 2.5 Flash via the official google-genai SDK.
"""

import json
import re
import pandas as pd
from google import genai


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


class FeedbackTriageAgent:
    """Product feedback triage agent powered by Gemini 2.5 Flash."""

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash-lite"

    # ------------------------------------------------------------------
    # Step 1: Categorization + Self-validation (single LLM call)
    # ------------------------------------------------------------------

    async def categorize_and_validate(
        self, feedbacks: list[str]
    ) -> tuple[list[dict], list[dict]]:
        """
        Categorizes feedbacks AND self-corrects in a single LLM call.
        Returns (final_items, corrections_list).
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

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        data = self._parse_json_response(self._extract_text(response))
        return data.get("feedbacks", []), data.get("corrections", [])

    # ------------------------------------------------------------------
    # Step 2: Executive report
    # ------------------------------------------------------------------

    async def generate_report(self, items: list[dict]) -> str:
        """Generates a PM executive report from the categorized feedbacks."""
        df = pd.DataFrame(items)

        category_stats = df["category"].value_counts().to_dict()
        priority_stats = df["priority"].value_counts().to_dict()
        sentiment_stats = df["sentiment"].value_counts().to_dict()

        high_priority = (
            df[df["priority"] == "High"][["summary", "category"]]
            .head(5)
            .to_dict("records")
        )

        prompt = f"""You are a senior Product Manager. Generate an executive report based on this analysis of {len(items)} user feedbacks.

STATISTICS:
- By category : {json.dumps(category_stats, ensure_ascii=False)}
- By priority : {json.dumps(priority_stats, ensure_ascii=False)}
- By sentiment: {json.dumps(sentiment_stats, ensure_ascii=False)}
- High-priority feedbacks: {json.dumps(high_priority, ensure_ascii=False)}

Generate the report using EXACTLY this markdown structure:

## Summary
[2-3 sentences on the overall product perception from users.]

## Top 3 Recommended Actions
1. **[Action]** — [Short impact-oriented justification]
2. **[Action]** — [Short impact-oriented justification]
3. **[Action]** — [Short impact-oriented justification]

## Weak Signal to Watch
[1 non-obvious insight or emerging trend worth investigating]

Be concise, factual and decision-oriented. Tone of a senior product consultant."""

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return self._extract_text(response)

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
        """Cleans and parses the LLM JSON response."""
        if not text:
            return {}
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```", "", text)
        text = text.strip()
        return json.loads(text)
