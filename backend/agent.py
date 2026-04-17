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

try:
    from openai import AsyncOpenAI as _AsyncOpenAI
except ImportError:
    _AsyncOpenAI = None  # type: ignore

try:
    from mistralai import Mistral as _Mistral
except ImportError:
    _Mistral = None  # type: ignore

# ------------------------------------------------------------------
# Lazy embedding model (sentence-transformers, loaded on first use)
# ------------------------------------------------------------------

_embedding_model = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


# ------------------------------------------------------------------
# Semantic clustering
# ------------------------------------------------------------------

_PRIORITY_SCORE = {"High": 3, "Medium": 1, "Low": 0}


def _cluster_items(items: list[dict]) -> list[dict]:
    """
    Clusters feedback items by semantic similarity of their Iris summaries.
    Returns clusters sorted by priority score desc (High=3, Medium=1, Low=0).
    Each cluster dict: {score, representative_summary, category, items}.
    """
    import numpy as np
    from sklearn.cluster import KMeans

    n_clusters = min(8, max(3, len(items) // 10))
    n_clusters = min(n_clusters, len(items))

    summaries = [item.get("summary") or "" for item in items]
    embeddings = _get_embedding_model().encode(summaries, convert_to_numpy=True)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(embeddings)

    cluster_map: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        cluster_map.setdefault(int(label), []).append(idx)

    result = []
    for label, indices in cluster_map.items():
        cluster_items = [items[i] for i in indices]
        score = sum(_PRIORITY_SCORE.get(it.get("priority", "Low"), 0) for it in cluster_items)

        # Representative feedback: closest to centroid
        cluster_embs = np.array([embeddings[i] for i in indices])
        centroid = kmeans.cluster_centers_[label]
        distances = np.linalg.norm(cluster_embs - centroid, axis=1)
        rep_local = int(distances.argmin())
        representative = cluster_items[rep_local]

        # Majority category
        cats = [it.get("category", "") for it in cluster_items]
        majority_cat = max(set(cats), key=cats.count)

        result.append({
            "score": score,
            "representative_summary": representative.get("summary", ""),
            "category": majority_cat,
            "items": cluster_items,
        })

    result.sort(key=lambda x: x["score"], reverse=True)

    # Tag each item with its cluster_id and cluster_label
    for cluster_id, cluster in enumerate(result):
        for item in cluster["items"]:
            item["cluster_id"] = cluster_id
            item["cluster_label"] = cluster["representative_summary"]

    return result


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
# priority, priority_reason + corrections) + fixed overhead
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

    def __init__(
        self,
        api_key: str,
        groq_api_key: str | None = None,
        openrouter_api_key: str | None = None,
        mistral_api_key: str | None = None,
    ):
        self.client = genai.Client(api_key=api_key)
        self.groq_client = AsyncGroq(api_key=groq_api_key) if groq_api_key else None
        self.openrouter_client = (
            _AsyncOpenAI(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1")
            if openrouter_api_key and _AsyncOpenAI is not None else None
        )
        self.mistral_client = (
            _Mistral(api_key=mistral_api_key)
            if mistral_api_key and _Mistral is not None else None
        )

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
- actionable  : true if the feedback contains specific, identifiable product information
                (a concrete bug, a precise feature request, a reproducible UX issue, etc.)
                false if it is purely emotional, generic, or contains no actionable product signal
                (e.g. "worst app ever", "I hate this", "dumbest ai" with no further detail)

═══ PHASE 2 — SELF-CORRECTION ═══
Review your own decisions critically:
- Is the category truly the most accurate one?
- Is the priority consistent with the real product impact?
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
      "actionable": true
    }}
  ],
  "corrections": [
    {{
      "id": <corrected feedback id>,
      "field": "category" | "priority",
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

    async def _call_llm_iris(self, prompt: str, n_feedbacks: int | None = None) -> tuple[str, bool]:
        """
        Iris call chain: Groq → OpenRouter → Gemini.
        Returns (text, used_fallback) where used_fallback=True if Groq was unavailable.
        """
        import asyncio as _asyncio

        n = n_feedbacks or 25
        max_tokens = min(FALLBACK_MODEL_MAX_TOKENS, _TOKENS_OVERHEAD + n * _TOKENS_PER_FEEDBACK)
        errors: list[str] = []

        # 1. Groq
        if self.groq_client:
            try:
                response = await self.groq_client.chat.completions.create(
                    model=FALLBACK_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content, False
            except Exception as e:
                errors.append(f"Groq: {e}")

        # 2. OpenRouter (NVIDIA Nemotron 3 Super 120B — infra NVIDIA, independent of Google/Groq)
        if self.openrouter_client:
            try:
                response = await self.openrouter_client.chat.completions.create(
                    model="nvidia/nemotron-3-super-120b-a12b:free",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content, True
            except Exception as e:
                errors.append(f"OpenRouter: {e}")

        # 3. Gemini — last resort, with retries on 503
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self.client.aio.models.generate_content(
                    model=PRIMARY_MODEL, contents=prompt
                )
                return self._extract_text(response), True
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_retryable = "503" in error_str or "UNAVAILABLE" in error_str or "high demand" in error_str.lower()
                if is_retryable and attempt < 2:
                    await _asyncio.sleep(2 ** attempt)
                    continue
                is_quota = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower()
                if is_quota:
                    errors.append(f"Gemini: {error_str[:150]}")
                    raise RuntimeError(
                        "All Iris models exhausted (Groq → OpenRouter → Gemini). "
                        "Try again in a few minutes. Details: " + " | ".join(errors)
                    ) from e
                raise
        raise last_error  # type: ignore[misc]

    async def _categorize_chunked(
        self, feedbacks: list[str], chunk_size: int
    ) -> tuple[list[dict], list[dict], bool]:
        """
        Processes feedbacks in chunks (Groq TPM limit = 25/chunk), all chunks in parallel.
        Returns (items, corrections, used_fallback) — True if any chunk used a fallback.
        """
        import asyncio as _asyncio

        chunks = [feedbacks[i: i + chunk_size] for i in range(0, len(feedbacks), chunk_size)]
        offsets = [i * chunk_size for i in range(len(chunks))]

        async def process_chunk(chunk: list[str], offset: int) -> tuple[list[dict], list[dict], bool]:
            prompt = self._build_categorization_prompt(chunk)
            text, chunk_fallback = await self._call_llm_iris(prompt, n_feedbacks=len(chunk))
            data = self._parse_json_response(text)
            chunk_items = data.get("feedbacks", [])
            chunk_corrections = [
                c for c in data.get("corrections", [])
                if c.get("old_value") != c.get("new_value")
            ]
            for item in chunk_items:
                item["id"] = offset + item["id"]
            for correction in chunk_corrections:
                correction["id"] = offset + correction["id"]
            return chunk_items, chunk_corrections, chunk_fallback

        results = await _asyncio.gather(*[process_chunk(chunk, offset) for chunk, offset in zip(chunks, offsets)])

        all_items: list[dict] = []
        all_corrections: list[dict] = []
        any_fallback = False
        for chunk_items, chunk_corrections, chunk_fallback in results:
            all_items.extend(chunk_items)
            all_corrections.extend(chunk_corrections)
            if chunk_fallback:
                any_fallback = True

        return all_items, all_corrections, any_fallback

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

        if max_tokens is None:
            n = n_feedbacks or 50
            max_tokens = min(FALLBACK_MODEL_MAX_TOKENS, _TOKENS_OVERHEAD + n * _TOKENS_PER_FEEDBACK)

        gemini_error = str(last_error) if 'last_error' in dir() else "unknown"  # type: ignore[name-defined]
        fallback_errors: list[str] = [f"Gemini: {gemini_error[:100]}"]

        # 2. Mistral Small
        if self.mistral_client:
            try:
                response = await self.mistral_client.chat.complete_async(
                    model="mistral-small-latest",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content, True
            except Exception as e:
                fallback_errors.append(f"Mistral: {e}")
        else:
            fallback_errors.append("Mistral: not configured (MISTRAL_API_KEY missing?)")

        # 3. OpenRouter (Nemotron 120B — NVIDIA infra, independent of Google/Groq)
        if self.openrouter_client:
            try:
                response = await self.openrouter_client.chat.completions.create(
                    model="nvidia/nemotron-3-super-120b-a12b:free",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content, True
            except Exception as e:
                fallback_errors.append(f"OpenRouter: {e}")

        # 4. Groq
        if self.groq_client:
            try:
                response = await self.groq_client.chat.completions.create(
                    model=FALLBACK_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content, True
            except Exception as e:
                fallback_errors.append(f"Groq: {e}")

        raise RuntimeError(
            "All Penn/Nova models exhausted (Gemini → Mistral → OpenRouter → Groq). "
            "Try again in a few minutes. Details: " + " | ".join(fallback_errors)
        )

    # ------------------------------------------------------------------
    # Step 1: Categorization + Self-validation (single LLM call)
    # ------------------------------------------------------------------

    async def categorize_and_validate(
        self, feedbacks: list[str]
    ) -> tuple[list[dict], list[dict], bool]:
        """
        Categorizes feedbacks AND self-corrects.
        Returns (final_items, corrections_list, used_fallback) — True if any chunk fell back from Groq.
        """
        items, corrections, used_fallback = await self._categorize_chunked(feedbacks, GROQ_CHUNK_SIZE)
        return items, corrections, used_fallback

    # ------------------------------------------------------------------
    # Step 2: Executive report
    # ------------------------------------------------------------------

    async def generate_report(self, items: list[dict], clusters: list[dict], app_name: str | None = None) -> tuple[str, list[str], bool]:
        """
        Generates a PM executive report from the categorized feedbacks.
        clusters must be pre-computed by _cluster_items (called externally so Echo step can be tracked).
        Returns (report_text, actions, used_fallback).
        """
        df = pd.DataFrame(items)
        priority_stats = df["priority"].value_counts().to_dict()

        # Build prompt context from top 6 clusters
        clusters_for_prompt = []
        for c in clusters[:6]:
            high_med = [it for it in c["items"] if it.get("priority") in ("High", "Medium")]
            verbatims = [it["original"][:200] for it in high_med[:3]]
            clusters_for_prompt.append({
                "priority_score": c["score"],
                "representative_summary": c["representative_summary"],
                "category": c["category"],
                "total_feedbacks": len(c["items"]),
                "high": sum(1 for it in c["items"] if it.get("priority") == "High"),
                "medium": sum(1 for it in c["items"] if it.get("priority") == "Medium"),
                "verbatims": verbatims,
            })

        app_context = f' for the app "{app_name}"' if app_name else ""
        app_rule = (
            f'- The product under review is "{app_name}". Mention it by name in the Summary section (at least once).\n'
            if app_name else ""
        )
        prompt = f"""You are a senior Product Manager. Generate an executive report based on this analysis of {len(items)} user feedbacks{app_context}.

OVERVIEW:
- By priority: {json.dumps(priority_stats, ensure_ascii=False)}

ISSUE CLUSTERS (semantically grouped, sorted by priority score — High=3pts, Medium=1pt, Low=0pt):
{json.dumps(clusters_for_prompt, ensure_ascii=False, indent=2)}

Each cluster includes:
- priority_score: sum of priority weights across all feedbacks in the cluster
- representative_summary: the most central feedback summary in the cluster
- verbatims: 1–3 real user quotes (original language) from High/Medium feedbacks in this cluster

Return ONLY valid JSON (no markdown, no surrounding text) with this exact structure:
{{
  "report": "## Summary\\n[2-3 sentences on overall product health, referencing specific issues from the top clusters.]\\n\\n## Top 3 Recommended Actions\\n1. **[Action title: verb + specific component/flow/feature]** — [What breaks or frustrates, evidence from verbatims, impact on retention]\\n2. **[same format]** — [same detail]\\n3. **[same format]** — [same detail]\\n\\n## Weak Signal to Watch\\n[1 non-obvious insight from a lower-ranked cluster]",
  "actions": ["exact action title 1", "exact action title 2", "exact action title 3"]
}}

Rules:
{app_rule}- Derive each action from one of the top 3 clusters in order of priority_score
- Action titles must name the specific feature, screen, or behaviour (e.g. "Fix voice mode interruption on iOS" not "fix bugs")
- Justify each action with data from the cluster's verbatims and counts
- Actions must be specific enough to copy directly as sprint backlog ticket titles
- Tone: senior product consultant, concise, decision-oriented
- The "actions" array must contain EXACTLY the bold titles from ## Top 3 Recommended Actions, verbatim"""

        text, used_fallback = await self._call_llm(prompt, max_tokens=2500)
        try:
            # Strip markdown fences and sanitize literal newlines inside JSON strings
            clean = re.sub(r"```(?:json)?\s*\n?", "", text)
            clean = re.sub(r"\n?```", "", clean).strip()
            # Replace literal newlines inside JSON string values with \n escape
            clean = re.sub(r'(?<=": ")(.*?)(?="[,\n}\]])', lambda m: m.group(0).replace("\n", "\\n"), clean, flags=re.DOTALL)
            parsed = json.loads(clean)
            report_md = parsed.get("report", clean)
            actions = parsed.get("actions", [])
        except Exception:
            # Last resort: extract report field with regex
            m = re.search(r'"report"\s*:\s*"(.*?)"(?=\s*,\s*"actions")', text, re.DOTALL)
            if m:
                report_md = m.group(1).replace("\\n", "\n").replace('\\"', '"')
                actions_m = re.findall(r'"([^"]+)"', text.split('"actions"')[-1])
                actions = actions_m[:3] if actions_m else []
            else:
                # Strip fences at minimum so raw JSON isn't shown
                report_md = re.sub(r"```(?:json)?\s*\n?|\n?```", "", text).strip()
                actions = []
        return report_md, actions, used_fallback

    async def generate_user_stories(
        self, clusters: list[dict], actions: list[str]
    ) -> tuple[list[dict], bool]:
        """
        Generates actionable sprint cards for each of the 3 recommended actions.
        Each action maps to the corresponding top cluster (clusters[0] → action 0, etc.).
        Format adapts to action type (bug, feature, ux, etc.) and includes RICE scoring.
        Returns (cards, used_fallback).
        """
        # Build per-action feedback lists from the top 3 clusters
        per_action_feedbacks = []
        for i, action in enumerate(actions[:3]):
            if i < len(clusters):
                cluster_items = clusters[i]["items"]
            else:
                # Fallback: shouldn't happen, but use all items as safety net
                cluster_items = [it for c in clusters for it in c["items"]]
            feedbacks = [
                {"original": it["original"], "summary": it.get("summary", ""), "priority": it.get("priority", "")}
                for it in cluster_items
            ]
            per_action_feedbacks.append({"action": action, "feedbacks": feedbacks})

        actions_str = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions))
        feedbacks_str = json.dumps(per_action_feedbacks, ensure_ascii=False, indent=2)

        total_items = sum(len(c["items"]) for c in clusters)
        prompt = f"""You are a senior Product Manager writing actionable sprint cards.

THE 3 RECOMMENDED ACTIONS:
{actions_str}

USER FEEDBACKS PER ACTION (each action is pre-matched to its semantic cluster of feedbacks):
{feedbacks_str}

Total feedbacks analyzed: {total_items}

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
- reach: integer count of feedbacks in this action's cluster that directly address this issue
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
        """Cleans and parses the LLM JSON response. Handles truncated JSON. Never raises."""
        if not text:
            return {}
        text = text.strip()
        # Strip <think>...</think> reasoning blocks (Nemotron, DeepSeek R1, etc.)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```", "", text)
        text = text.strip()
        if not text:
            return {}

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON object {...} from surrounding text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Response was likely truncated — attempt to recover the feedbacks array
        match = re.search(r'"feedbacks"\s*:\s*(\[.*)', text, re.DOTALL)
        if match:
            array_text = match.group(1)
            last_complete = array_text.rfind("},")
            if last_complete == -1:
                last_complete = array_text.rfind("}")
            if last_complete != -1:
                try:
                    feedbacks = json.loads(array_text[: last_complete + 1] + "]")
                    return {"feedbacks": feedbacks, "corrections": []}
                except json.JSONDecodeError:
                    pass

        # Nothing worked — log and return empty so the chunk is skipped gracefully
        import logging as _logging
        _logging.getLogger("triage").warning(
            "_parse_json_response: could not parse response (first 300 chars): %s", text[:300]
        )
        return {}
