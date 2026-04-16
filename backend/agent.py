"""
agent.py — Core logic of the product feedback triage agent.

Model routing:
  - Iris  (categorization) : Groq / Llama 3.3 70B as primary — fast structured JSON,
                             falls back to Gemini if Groq is unavailable.
  - Hugo  (report)         : Gemini 2.5 Flash as primary — best free-tier quality
                             for narrative synthesis, falls back to Groq.
  - Stella (backlog cards) : Gemini 2.5 Flash as primary, falls back to Groq.
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
- actionable  : true if the feedback contains specific, identifiable product information
                (a concrete bug, a precise feature request, a reproducible UX issue, etc.)
                false if it is purely emotional, generic, or contains no actionable product signal
                (e.g. "worst app ever", "I hate this", "dumbest ai" with no further detail)

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
      "sentiment": "...",
      "actionable": true
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

IMPORTANT RULES FOR CORRECTIONS:
- Only include a correction when old_value and new_value are DIFFERENT.
- Never list a correction just to confirm a decision was correct.
- If a field needed no change, do NOT include it in corrections at all.
- If no fields needed changing, return "corrections": []."""

    async def _call_llm_iris(self, prompt: str, n_feedbacks: int | None = None) -> str:
        """
        Groq-primary LLM call for Iris (categorization).
        Tries Groq/Llama 3.3 70B first; falls back to Gemini (with retries on 503) if Groq fails.
        """
        import asyncio as _asyncio

        groq_error: Exception | None = None
        if self.groq_client:
            n = n_feedbacks or 25
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
                return response.choices[0].message.content
            except Exception as e:
                groq_error = e  # fall through to Gemini

        # Gemini fallback — with retries on transient 503/UNAVAILABLE
        last_error: Exception | None = None
        for attempt in range(3):  # 1 initial + 2 retries
            try:
                response = await self.client.aio.models.generate_content(
                    model=PRIMARY_MODEL, contents=prompt
                )
                return self._extract_text(response)
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_retryable = "503" in error_str or "UNAVAILABLE" in error_str or "high demand" in error_str.lower()
                if is_retryable and attempt < 2:
                    await _asyncio.sleep(2 ** attempt)  # 1s, 2s
                    continue
                # Both Groq and Gemini failed — build a friendly combined message
                is_quota = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower()
                if is_quota and self.groq_client:
                    raise RuntimeError(
                        "Daily quota exhausted on both Groq and Gemini free tiers — "
                        "retry in a few minutes (Groq rate limit resets quickly) "
                        "or tomorrow (Gemini daily quota resets at midnight Pacific). "
                        f"Groq error: {type(groq_error).__name__ if groq_error else 'n/a'} — "
                        f"Gemini error: {error_str[:200]}"
                    ) from e
                raise
        raise last_error  # type: ignore[misc]

    async def _categorize_chunked(
        self, feedbacks: list[str], chunk_size: int
    ) -> tuple[list[dict], list[dict]]:
        """
        Processes feedbacks in chunks (Groq TPM limit = 25/chunk).
        Uses Groq as primary per chunk, Gemini as fallback.
        Merges results and re-sequences IDs globally.
        """
        all_items: list[dict] = []
        all_corrections: list[dict] = []
        global_offset = 0

        for i in range(0, len(feedbacks), chunk_size):
            chunk = feedbacks[i : i + chunk_size]
            prompt = self._build_categorization_prompt(chunk)
            text = await self._call_llm_iris(prompt, n_feedbacks=len(chunk))
            data = self._parse_json_response(text)
            chunk_items = data.get("feedbacks", [])
            chunk_corrections = [
                c for c in data.get("corrections", [])
                if c.get("old_value") != c.get("new_value")
            ]

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
        Calls the primary model (Gemini) with up to 2 retries on transient errors
        (503 UNAVAILABLE, high demand), then falls back to Groq on quota/persistent errors.
        Returns (response_text, used_fallback).
        Raises if both models fail or Groq is not configured.
        """
        import asyncio as _asyncio

        def _is_retryable(error_str: str) -> bool:
            return "503" in error_str or "UNAVAILABLE" in error_str or "high demand" in error_str.lower()

        def _is_quota(error_str: str) -> bool:
            return "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

        # Try Gemini first (unless forced to Groq for chunked calls)
        if not _force_groq:
            last_error = None
            for attempt in range(3):  # 1 initial + 2 retries
                try:
                    response = await self.client.aio.models.generate_content(
                        model=PRIMARY_MODEL,
                        contents=prompt,
                    )
                    return self._extract_text(response), False

                except Exception as e:
                    error_str = str(e)
                    last_error = e

                    if _is_retryable(error_str) and attempt < 2:
                        # Transient overload — wait and retry
                        await _asyncio.sleep(2 ** attempt)  # 1s, 2s
                        continue
                    elif _is_quota(error_str) or _is_retryable(error_str):
                        # Quota exhausted or still failing after retries — go to Groq
                        break
                    else:
                        raise  # Unexpected error: propagate immediately

            # All Gemini attempts failed with quota/overload
            _ = last_error  # suppress unused warning

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
        Categorizes feedbacks AND self-corrects.
        Iris always uses Groq/Llama 3.3 70B (chunked) as primary model.
        Returns (final_items, corrections_list, used_fallback=False — Groq is intentional).
        """
        items, corrections = await self._categorize_chunked(feedbacks, GROQ_CHUNK_SIZE)
        return items, corrections, False

    # ------------------------------------------------------------------
    # Step 2: Executive report
    # ------------------------------------------------------------------

    async def generate_report(self, items: list[dict], app_name: str | None = None) -> tuple[str, bool]:
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

        app_context = f' for the app "{app_name}"' if app_name else ""
        app_rule = (
            f'- The product under review is "{app_name}". Mention it by name in the Summary section (at least once).\n'
            if app_name else ""
        )
        prompt = f"""You are a senior Product Manager. Generate an executive report based on this analysis of {len(items)} user feedbacks{app_context}.

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
{app_rule}- Action titles: name the specific feature/flow (e.g. "Fix appointment date picker crash on iOS" not "fix bugs")
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
        Generates actionable sprint cards for each of the 3 recommended actions.
        Format adapts to action type (bug, feature, ux, etc.) and includes RICE scoring.
        Returns (cards, used_fallback).
        """
        df = pd.DataFrame(items)
        mask = df["priority"].isin(["High", "Medium"])
        if "actionable" in df.columns:
            mask = mask & (df["actionable"] != False)  # noqa: E712
        high_medium = df[mask][
            ["original", "summary", "category", "priority"]
        ].to_dict(orient="records")

        actions_str = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions))
        feedbacks_str = json.dumps(high_medium, ensure_ascii=False, indent=2)

        prompt = f"""You are a senior Product Manager writing actionable sprint cards.

THE 3 RECOMMENDED ACTIONS:
{actions_str}

HIGH/MEDIUM PRIORITY USER FEEDBACKS (total analyzed: {len(items)}):
{feedbacks_str}

For each action, produce a card following these steps:

STEP 1 — Detect action_type: "bug" | "performance" | "feature" | "ux" | "pricing" | "ai_quality" | "other"
  Use "ai_quality" when the action addresses the quality, tone, accuracy, or relevance of AI-generated responses.

STEP 2 — Select 2–4 quotes STRICTLY relevant to this action's specific topic.
STRICT RELEVANCE: only include a quote if its content directly and specifically addresses this action.
Never include generic complaints or praise that could apply to any issue.
If fewer than 2 quotes qualify, include only those that do.
For each selected quote, detect its language. If it is NOT English, add an "translation" field
with a concise English translation. If it IS English, omit the "translation" field entirely.

STEP 3 — Estimate RICE:
- reach: integer count of feedbacks (from the full list above) that directly mention this issue
- impact: 1=low friction | 2=significant friction or churn risk | 3=blocking or critical
- confidence: 0.2 to 1.0 — how reliable are your estimates of R, I and E?
    Independent of reach. Ask: "How sure am I that these numbers are right?"
    * 0.8–1.0 : issue is clearly defined and reproducible; impact and effort estimates are well-grounded
    * 0.5–0.7 : estimates are reasonable but uncertain — root cause unclear, impact could vary, effort hard to scope
    * 0.2–0.4 : significant uncertainty in at least one estimate — vague problem, unknown complexity, or speculative impact
- effort_label: "XS" (hours) | "S" (days) | "M" (1–2 sprints) | "L" (3–4 sprints) | "XL" (quarter+)
- effort: XS=0.5, S=1, M=2, L=4, XL=8
- score: integer, formula = round((reach * impact * confidence / effort) * 10)

STEP 4 — Fill the template matching action_type:
- bug or performance → provide: what_breaks, done_when, next_step
- feature → provide: user_story ("As a [type], I want [X] so that [Y]"), acceptance_criteria (2–4 testable Given/When/Then strings)
- ux, pricing, other → provide: problem, success_metric, next_step

Return ONLY a valid JSON array, no markdown, no surrounding text:
[
  {{
    "action": "exact action title verbatim",
    "action_type": "bug",
    "feedbacks": [
      {{"text": "verbatim quote in original language", "translation": "English translation"}},
      {{"text": "verbatim English quote"}}
    ],
    "rice": {{"reach": 12, "impact": 3, "confidence": 0.8, "effort_label": "M", "effort": 2, "score": 144}},
    "what_breaks": "Concise description of what fails and when",
    "done_when": "Observable, testable completion criteria",
    "next_step": "Concrete first engineering or design action"
  }},
  {{
    "action": "exact action title verbatim",
    "action_type": "feature",
    "feedbacks": [
      {{"text": "verbatim English quote"}}
    ],
    "rice": {{"reach": 6, "impact": 2, "confidence": 0.7, "effort_label": "L", "effort": 4, "score": 21}},
    "user_story": "As a [user type], I want [specific thing] so that [concrete benefit]",
    "acceptance_criteria": [
      "Given [context], when [action], then [expected result]",
      "Given [context], when [action], then [expected result]"
    ]
  }},
  {{
    "action": "exact action title verbatim",
    "action_type": "ux",
    "feedbacks": [
      {{"text": "verbatim English quote"}}
    ],
    "rice": {{"reach": 5, "impact": 2, "confidence": 0.6, "effort_label": "S", "effort": 1, "score": 60}},
    "problem": "Clear problem statement from the user's perspective",
    "success_metric": "How you will measure that this is resolved",
    "next_step": "Concrete first action (design, A/B test, research, etc.)"
  }}
]"""

        text, used_fallback = await self._call_llm(prompt, max_tokens=3000)
        try:
            clean = re.sub(r"```(?:json)?\s*\n?", "", text)
            clean = re.sub(r"\n?```", "", clean).strip()
            cards = json.loads(clean)
            if not isinstance(cards, list):
                raise ValueError
            # Strip redundant English→English "translation" fields
            def _norm(s: str) -> str:
                return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
            for card in cards:
                for fb in card.get("feedbacks", []) or []:
                    tr = fb.get("translation")
                    if tr and _norm(tr) == _norm(fb.get("text", "")):
                        fb.pop("translation", None)
            # Sort by RICE score descending
            cards.sort(key=lambda c: c.get("rice", {}).get("score", 0), reverse=True)
        except Exception as e:
            print(f"[generate_user_stories] parse error: {e}\nRaw output: {text[:500]}")
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
