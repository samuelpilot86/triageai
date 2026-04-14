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

# Groq free tier: 12 000 TPM (input + output combined).
# At ~1 500 tokens of input overhead + 250 per feedback output,
# max safe feedbacks per call = floor((12000 - 1500) / 250) = 42.
# Use 25 for a balance between safety margin and number of API calls.
# 100 feedbacks → 4 chunks of 25 (vs 5 chunks of 20 before).
GROQ_CHUNK_SIZE = 25


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

    def _build_categorization_prompt(self, feedbacks: list[str]) -> str:
        """Builds the categorization+validation prompt for a list of feedbacks."""
        feedbacks_numbered = "\n".join(
            [f"{i + 1}. {f}" for i, f in enumerate(feedbacks)]
        )
        categories_str = ", ".join(CATEGORIES)
        return f"""You are an expert product feedback analyst. Work in two phases.

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

    async def _categorize_chunked(
        self, feedbacks: list[str], chunk_size: int
    ) -> tuple[list[dict], list[dict]]:
        """
        Processes feedbacks in chunks to stay within Groq TPM limits.
        Merges results and re-sequences IDs globally.
        """
        all_items: list[dict] = []
        all_corrections: list[dict] = []
        global_offset = 0

        for i in range(0, len(feedbacks), chunk_size):
            chunk = feedbacks[i : i + chunk_size]
            prompt = self._build_categorization_prompt(chunk)
            text, _ = await self._call_llm(
                prompt, n_feedbacks=len(chunk), _force_groq=True
            )
            data = self._parse_json_response(text)
            chunk_items = data.get("feedbacks", [])
            chunk_corrections = data.get("corrections", [])

            # Re-sequence IDs globally across chunks
            for item in chunk_items:
                item["id"] = global_offset + item["id"]
            for correction in chunk_corrections:
                correction["id"] = global_offset + correction["id"]

            all_items.extend(chunk_items)
            all_corrections.extend(chunk_corrections)
            global_offset += len(chunk)

        return all_items, all_corrections

    async def _call_llm(self, prompt: str, n_feedbacks: int | None = None, max_tokens: int | None = None, _force_groq: bool = False) -> tuple[str, bool]:
        """
        Calls the primary model (Gemini). If quota is exhausted (429),
        falls back to Groq automatically.
        Returns (response_text, used_fallback).
        Raises if both models fail or Groq is not configured.
        """
        # Try Gemini first (unless forced to Groq for chunked calls)
        if not _force_groq:
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

        if not self.groq_client:
            raise RuntimeError(
                "Gemini quota exhausted and no GROQ_API_KEY configured. "
                "Please set GROQ_API_KEY in your Space secrets to enable fallback."
            )

        if max_tokens is None:
            n = n_feedbacks or 50
            max_tokens = min(
                FALLBACK_MODEL_MAX_TOKENS,
                _TOKENS_OVERHEAD + n * _TOKENS_PER_FEEDBACK,
            )
        try:
            response = await self.groq_client.chat.completions.create(
                model=FALLBACK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content, True
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                raise RuntimeError(
                    "Daily quota exhausted on both Gemini and Groq (free tiers). "
                    "Please try again later — Groq resets every 24h, Gemini resets every minute."
                )
            raise

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
        prompt = self._build_categorization_prompt(feedbacks)

        try:
            text, used_fallback = await self._call_llm(prompt, n_feedbacks=len(feedbacks))
            data = self._parse_json_response(text)
            return data.get("feedbacks", []), data.get("corrections", []), used_fallback
        except Exception as e:
            error_str = str(e)
            is_quota = (
                "429" in error_str
                or "RESOURCE_EXHAUSTED" in error_str
                or "413" in error_str
                or "Request too large" in error_str
            )
            if not is_quota or not self.groq_client:
                raise
            items, corrections = await self._categorize_chunked(feedbacks, GROQ_CHUNK_SIZE)
            return items, corrections, True

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

Return ONLY valid JSON (no markdown, no surrounding text) with this exact structure:
{{
  "report": "## Summary\\n[2-3 sentences on overall product health, referencing dominant issue themes specifically.]\\n\\n## Top 3 Recommended Actions\\n1. **[Action title: verb + specific component/flow]** — [What breaks, how many users, impact on retention]\\n2. **[same format]** — [same detail]\\n3. **[same format]** — [same detail]\\n\\n## Weak Signal to Watch\\n[1 non-obvious insight]",
  "actions": ["exact action title 1", "exact action title 2", "exact action title 3"]
}}

Rules for report content:
- Action titles: name the specific feature/flow (e.g. "Fix appointment date picker crash on iOS" not "fix bugs")
- If multiple distinct issues share a category, pick the most impactful — mention others in justification
- Include counts/percentages to justify prioritization
- Actions must be specific enough to copy directly as a sprint backlog ticket title
- Tone: senior product consultant, concise, decision-oriented
- The "actions" array must contain EXACTLY the bold titles from ## Top 3 Recommended Actions, verbatim"""

        text, used_fallback = await self._call_llm(prompt, max_tokens=2500)
        try:
            parsed = self._parse_json_response(text)
            report_md = parsed.get("report", text)
            actions = parsed.get("actions", [])
        except Exception:
            report_md = text
            actions = []
        return report_md, actions, used_fallback

    async def generate_user_stories(
        self, items: list[dict], actions: list[str]
    ) -> tuple[list[dict], bool]:
        """
        Generates Key User Feedback cards for each of the 3 recommended actions.
        Returns (cards, used_fallback).
        Each card: {action, feedbacks: [str], user_stories: [{title, acceptance_criteria: [str]}]}
        """
        df = pd.DataFrame(items)
        high_medium = df[df["priority"].isin(["High", "Medium"])][
            ["original", "summary", "category", "priority"]
        ].to_dict(orient="records")

        actions_str = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions))
        feedbacks_str = json.dumps(high_medium, ensure_ascii=False, indent=2)

        prompt = f"""You are a senior Product Manager writing user story cards for a sprint backlog.

THE 3 RECOMMENDED ACTIONS:
{actions_str}

HIGH/MEDIUM PRIORITY USER FEEDBACKS:
{feedbacks_str}

For each action, produce a structured card containing:
1. The exact action title (verbatim from the list above)
2. The 3–5 user feedback quotes (use "original" field) that most directly justify this action
3. 1–2 user stories in the format "As a [user type], I want [specific feature/fix] so that [concrete benefit]", each with 2–4 acceptance criteria

Return ONLY valid JSON, no markdown, no surrounding text:
[
  {{
    "action": "exact action title",
    "feedbacks": ["original quote 1", "original quote 2", "original quote 3"],
    "user_stories": [
      {{
        "title": "As a [user type], I want [X] so that [Y]",
        "acceptance_criteria": [
          "Given [context], when [action], then [expected result]",
          "..."
        ]
      }}
    ]
  }}
]

Rules:
- Use verbatim quotes from the "original" field — do not paraphrase
- User story titles must be specific and actionable, not generic
- Acceptance criteria must be testable (Given/When/Then format preferred)
- Each card must have at least 1 user story, at most 2"""

        text, used_fallback = await self._call_llm(prompt, max_tokens=3000)
        try:
            cards = json.loads(self._parse_json_response(text).__class__.__name__ and text.strip())
            if not isinstance(cards, list):
                raise ValueError
        except Exception:
            try:
                # _parse_json_response expects a dict, handle list directly
                clean = re.sub(r"```(?:json)?\s*\n?", "", text)
                clean = re.sub(r"\n?```", "", clean).strip()
                cards = json.loads(clean)
            except Exception:
                cards = []
        return cards, used_fallback

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
