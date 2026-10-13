"""
agent.py — Core logic of the product feedback triage agent.

Model routing:
  - Sift  (pre-filter)     : Cerebras / gpt-oss-120b first — binary filter, tiny output.
                             Falls back to Gemini 3.1 Flash Lite.
  - Iris  (split + action) : Gemini 3.1 Flash Lite — verbatim excerpts, a shippable action name,
                             a category, and a refusal when the action cannot be named.
                             Falls back to Groq Qwen 3.8 27B in instruct mode.
  - Echo  (clustering)     : Cerebras / gpt-oss-120b first — merges action names already written by Iris.
                             Falls back to Gemini.
  - Nova  (sprint cards)   : Gemini 3.1 Flash Lite — one RICE card per action.
                             Falls back to Cerebras GLM 4.7.
  The executive report (Penn) lives in parked_report.py and is not called.
"""

from __future__ import annotations

import asyncio
import json
import re
from google import genai
from groq import AsyncGroq

from excerpts import accept_elements, settle_clusters

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

def _cluster_items(items: list[dict]) -> list[dict]:
    """
    Clusters feedback items by semantic similarity of their Iris summaries.
    score is the number of feedbacks in the cluster. Ticket order is RICE, later.
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
        score = len(cluster_items)

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

def _require_content(response, source: str) -> str:
    """Extract text content from an OpenAI-compatible response, raising if None."""
    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError(f"{source} returned null content (model may have refused or timed out)")
    return content


IRIS_MODEL = "gemini-3.1-flash-lite-preview"   # Gemini 3.1 Flash Lite: 250K TPM, 500 RPD free
CEREBRAS_STRUCTURED_MODEL = "gpt-oss-120b"              # Sift, Echo — fast MoE, 5.1B active params
CEREBRAS_NARRATIVE_MODEL = "zai-glm-4.7"  # Nova — GLM 4.7 (Zhipu/Z.ai); replaces Qwen 235B (retired May 27 2026); 100 RPD free
FALLBACK_MODEL = "qwen/qwen3.8-27b"  # Groq last-resort; successor to qwen-3.6-27b (decommissioned 14 Sep 2026)
FALLBACK_MODEL_MAX_TOKENS = 16_384  # Groq max completion tokens for Qwen 3.8 27B

# Output token budget per kept review. A review can yield several excerpts.
_TOKENS_PER_FEEDBACK = 400
_TOKENS_OVERHEAD = 512

# Groq free tier: 12 000 TPM (input + output combined).
# Chunk size stays at 30 so a kept review can yield more than one excerpt
# without blowing the output budget on the fallback model.
GROQ_CHUNK_SIZE = 30
SIFT_CHUNK_SIZE = 25   # Sift parallelization: 25 feedbacks/chunk → 4 parallel calls on 100 feedbacks


_RICE_IMPACT = (0.25, 0.5, 1.0, 2.0, 3.0)


def _normalize_rice(card: dict) -> None:
    """Snap impact onto Intercom's scale and recompute the score from the formula."""
    rice = card.get("rice")
    if not isinstance(rice, dict):
        return
    try:
        raw = float(rice.get("impact"))
    except (TypeError, ValueError):
        raw = 1.0
    impact = min(_RICE_IMPACT, key=lambda step: abs(step - raw))
    rice["impact"] = impact if impact < 1 else int(impact)
    try:
        reach = float(rice.get("reach") or 0)
        confidence = float(rice.get("confidence") or 0)
        effort = float(rice.get("effort") or 0)
    except (TypeError, ValueError):
        return
    if effort > 0:
        rice["score"] = int(round((reach * impact * confidence / effort) * 10))


class FeedbackTriageAgent:
    """
    Product feedback triage agent.
    Primary: Cerebras (Sift/Echo: gpt-oss-120b) + Gemini 3.1 Flash Lite (Iris, Nova).
    Fallbacks: Cerebras GLM 4.7 → Mistral → OpenRouter → Groq Qwen 3.8 27B.
    """

    def __init__(
        self,
        api_key: str,
        groq_api_key: str | None = None,
        openrouter_api_key: str | None = None,
        mistral_api_key: str | None = None,
        cerebras_api_key: str | None = None,
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
        self.cerebras_client = (
            _AsyncOpenAI(api_key=cerebras_api_key, base_url="https://api.cerebras.ai/v1")
            if cerebras_api_key and _AsyncOpenAI is not None else None
        )

    # ------------------------------------------------------------------
    # Cerebras helper
    # ------------------------------------------------------------------

    async def _call_cerebras(self, model: str, prompt: str, max_tokens: int = 2500) -> str:
        """Single Cerebras call. Raises on failure (caller handles fallback)."""
        if self.cerebras_client is None:
            raise RuntimeError("Cerebras client not configured")
        response = await self.cerebras_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return _require_content(response, f"Cerebras/{model}")

    async def _call_groq(self, prompt: str, max_tokens: int) -> str:
        """Groq last-resort call. Instruct mode (no thinking) keeps JSON/prose clean."""
        if self.groq_client is None:
            raise RuntimeError("Groq client not configured")
        response = await self.groq_client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=max_tokens,
            extra_body={"reasoning_effort": "none"},
        )
        return _require_content(response, "Groq")

    # ------------------------------------------------------------------
    # Central LLM call with fallback
    # ------------------------------------------------------------------

    def _build_categorization_prompt(self, feedbacks: list[tuple[int, str]]) -> str:
        """Ask Iris for one or more verbatim excerpts per kept review."""
        feedbacks_numbered = "\n".join(f"{source_id}. {text}" for source_id, text in feedbacks)
        categories_str = ", ".join(CATEGORIES)
        return f"""You are an expert product feedback analyst. Work in two phases.

FEEDBACKS TO ANALYZE:
{feedbacks_numbered}

═══ PHASE 1 — SPLIT INTO ACTIONABLE ELEMENTS ═══
An actionable element is one shippable product action. It is distinct from the feedback it comes from.

For each feedback, return one or more elements:
- One element when the feedback contains a single shippable action. The excerpt is only the sentences that carry that action. Leave out praise, insults, and filler.
- Several elements when the feedback contains two or more distinct shippable actions, such as a bug and a separate feature request, or two different bugs. Each excerpt contains only the sentences for its own action.
- Do not create an element for a sentence that has no product action.

Each element:
- id        : integer, starts at 1, unique in this response
- source_id : the feedback number printed above. Copy that number.
- excerpt   : an exact contiguous copy of those sentences. Do not paraphrase, translate, shorten with an ellipsis, or add words. The excerpt must appear verbatim in that feedback.
- summary   : what this element asks for, 6 words or fewer
- action    : the shippable change, as a ticket title, 8 words or fewer. Name only what the excerpt itself says. Do not guess. Never use Other, Misc, Bugs, or a theme.
- category  : ONE of: {categories_str}

If a span suggests a wish but you cannot name the action without guessing, do not put it in elements. Put it in unclear.

═══ PHASE 2 — SELF-CORRECTION ═══
Review your own decisions critically:
- Is the category truly the most accurate one?
- Are there inconsistencies across similar elements?
- Does any excerpt still contain a second shippable action? If it does, replace that element with two elements in the array. Each new excerpt must still be a verbatim span of the same feedback.
- Is the action name a change a team could ship? If it is vague, or if naming it required a guess, move that element to unclear and remove it from elements.
Apply category corrections directly in the elements array, and log them.

Return ONLY valid JSON, no markdown, no surrounding text:
{{
  "elements": [
    {{
      "id": 1,
      "source_id": 1,
      "excerpt": "exact sentences copied from that feedback",
      "summary": "...",
      "action": "shippable change in a few words",
      "category": "..."
    }}
  ],
  "unclear": [
    {{
      "source_id": 2,
      "excerpt": "exact sentences that do not name an action",
      "reason": "why no ticket can be named, 10 words max"
    }}
  ],
  "corrections": [
    {{
      "id": <element id>,
      "field": "category",
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

    async def _call_llm_iris(self, prompt: str, n_feedbacks: int | None = None) -> tuple[str, str | None]:
        """
        Iris call chain: Gemini 3.1 Flash Lite → Groq → OpenRouter.
        Returns (text, fallback_provider) — None if Gemini succeeded, provider name otherwise.
        """
        import asyncio as _asyncio

        n = n_feedbacks or 25
        groq_max_tokens = min(FALLBACK_MODEL_MAX_TOKENS, _TOKENS_OVERHEAD + n * _TOKENS_PER_FEEDBACK)
        nemotron_max_tokens = min(4096, groq_max_tokens)
        errors: list[str] = []

        # 1. Gemini 3.1 Flash Lite — 250K TPM absorbs parallel chunks, 500 RPD free tier
        last_error: Exception | None = None
        for attempt in range(2):  # 1 retry on transient 503s, no retry on quota errors
            try:
                response = await self.client.aio.models.generate_content(
                    model=IRIS_MODEL, contents=prompt
                )
                return self._extract_text(response), None
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_retryable = "503" in error_str or "UNAVAILABLE" in error_str or "high demand" in error_str.lower()
                is_quota = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower()
                if is_quota:
                    errors.append(f"Gemini: {error_str[:150]}")
                    break
                elif is_retryable and attempt == 0:
                    await _asyncio.sleep(2)
                    continue
                elif is_retryable:
                    errors.append(f"Gemini: {error_str[:150]}")
                    break
                else:
                    raise

        # 2. Groq Qwen 3.8 27B — first fallback (Iris only)
        if self.groq_client:
            try:
                return await self._call_groq(prompt, groq_max_tokens), "Groq"
            except Exception as e:
                errors.append(f"Groq: {e}")

        # 3. OpenRouter — last resort
        if self.openrouter_client:
            try:
                response = await _asyncio.wait_for(
                    self.openrouter_client.chat.completions.create(
                        model="openrouter/auto",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        max_tokens=nemotron_max_tokens,
                    ),
                    timeout=90,
                )
                return _require_content(response, "OpenRouter/auto"), "OpenRouter"
            except Exception as e:
                errors.append(f"OpenRouter: {type(e).__name__}: {e}")

        raise RuntimeError(
            "All Iris models exhausted (Gemini → Groq → OpenRouter). "
            "Try again in a few minutes. Details: " + " | ".join(errors)
        )

    async def _categorize_chunked(
        self, feedbacks: list[tuple[int, str]], chunk_size: int
    ) -> tuple[list[dict], list[dict], list[dict], str | None]:
        """
        Splits kept reviews into verbatim elements, in parallel chunks.
        Returns (elements, unclear, corrections, fallback_provider).
        fallback_provider is None when Gemini handled every chunk.
        """
        import asyncio as _asyncio

        chunks = [feedbacks[i: i + chunk_size] for i in range(0, len(feedbacks), chunk_size)]

        async def process_chunk(chunk: list[tuple[int, str]]) -> tuple[list[dict], list[dict], list[dict], str | None]:
            prompt = self._build_categorization_prompt(chunk)
            text, chunk_provider = await self._call_llm_iris(prompt, n_feedbacks=len(chunk))
            data = self._parse_json_response(text)
            elements, unclear, corrections = accept_elements(chunk, data, set(CATEGORIES))
            return elements, unclear, corrections, chunk_provider

        results = await _asyncio.gather(*[process_chunk(chunk) for chunk in chunks])

        all_items: list[dict] = []
        all_unclear: list[dict] = []
        all_corrections: list[dict] = []
        fallback_provider: str | None = None
        next_id = 1
        for chunk_items, chunk_unclear, chunk_corrections, chunk_provider in results:
            local_to_global: dict[int, int] = {}
            for item in chunk_items:
                local_id = item.pop("_local_id", None)
                item["id"] = next_id
                if isinstance(local_id, int) and local_id not in local_to_global:
                    local_to_global[local_id] = next_id
                next_id += 1
                all_items.append(item)
            all_unclear.extend(chunk_unclear)
            for correction in chunk_corrections:
                local_id = correction.pop("_local_id", None)
                global_id = local_to_global.get(local_id)
                if global_id is None:
                    continue
                correction["id"] = global_id
                all_corrections.append(correction)
            if chunk_provider is not None and fallback_provider is None:
                fallback_provider = chunk_provider

        return all_items, all_unclear, all_corrections, fallback_provider

    async def _call_llm(
        self, prompt: str, max_tokens: int = 2500, cerebras_model: str = CEREBRAS_NARRATIVE_MODEL,
        prefer_cerebras: bool = False,
    ) -> tuple[str, str | None]:
        """
        Nova chain: Gemini 3.1 Flash Lite → Cerebras → Mistral → OpenRouter → Groq.
        Sift and Echo pass prefer_cerebras=True so gpt-oss-120b runs first and Gemini's
        daily quota stays on Iris and Nova. GLM 4.7 is only the Nova fallback.
        Returns (response_text, fallback_provider). None means the primary model succeeded.
        """
        import asyncio as _asyncio

        def _is_retryable(error_str: str) -> bool:
            return "503" in error_str or "UNAVAILABLE" in error_str or "high demand" in error_str.lower()

        def _is_quota(error_str: str) -> bool:
            return "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

        fallback_errors: list[str] = []
        groq_max_tokens = min(FALLBACK_MODEL_MAX_TOKENS, max_tokens)
        nemotron_max_tokens = min(4096, max_tokens)
        cerebras_tried = False

        if prefer_cerebras and self.cerebras_client:
            cerebras_tried = True
            try:
                return await self._call_cerebras(cerebras_model, prompt, max_tokens), None
            except Exception as e:
                fallback_errors.append(f"Cerebras: {e}")

        # Gemini 3.1 Flash Lite — primary for Nova, fallback for Sift and Echo.
        last_error = None
        for attempt in range(2):  # 1 retry on transient 503s, no retry on quota errors
            try:
                response = await self.client.aio.models.generate_content(
                    model=IRIS_MODEL,
                    contents=prompt,
                )
                text = self._extract_text(response)
                return text, ("Gemini" if prefer_cerebras else None)
            except Exception as e:
                error_str = str(e)
                last_error = e
                if _is_quota(error_str):
                    break
                elif _is_retryable(error_str) and attempt == 0:
                    await _asyncio.sleep(2)
                    continue
                elif _is_retryable(error_str):
                    break
                else:
                    raise
        fallback_errors.append(f"Gemini: {str(last_error)[:100] if last_error else 'unknown'}")

        # Cerebras — Nova fallback (GLM 4.7). Skipped when Sift or Echo already tried it.
        if self.cerebras_client and not cerebras_tried:
            try:
                return await self._call_cerebras(cerebras_model, prompt, max_tokens), "Cerebras"
            except Exception as e:
                fallback_errors.append(f"Cerebras: {e}")

        # 3. Mistral Small — separate quota, 2 RPM (slow but available)
        if self.mistral_client:
            try:
                response = await self.mistral_client.chat.complete_async(
                    model="mistral-small-latest",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                return _require_content(response, "Mistral"), "Mistral"
            except Exception as e:
                fallback_errors.append(f"Mistral: {e}")
        else:
            fallback_errors.append("Mistral: not configured")

        # 4. OpenRouter — last resort before Groq
        if self.openrouter_client:
            try:
                response = await _asyncio.wait_for(
                    self.openrouter_client.chat.completions.create(
                        model="openrouter/auto",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        max_tokens=nemotron_max_tokens,
                    ),
                    timeout=90,
                )
                return _require_content(response, "OpenRouter/auto"), "OpenRouter"
            except Exception as e:
                fallback_errors.append(f"OpenRouter: {type(e).__name__}: {e}")

        # 5. Groq Qwen 3.8 27B — last resort
        if self.groq_client:
            try:
                return await self._call_groq(prompt, groq_max_tokens), "Groq"
            except Exception as e:
                fallback_errors.append(f"Groq: {e}")

        raise RuntimeError(
            "All models exhausted (Gemini → Cerebras → Mistral → OpenRouter → Groq). "
            "Try again in a few minutes. Details: " + " | ".join(fallback_errors)
        )

    # ------------------------------------------------------------------
    # Sift — filter actionable feedbacks (single batched LLM call)
    # ------------------------------------------------------------------

    async def sift_feedbacks(self, feedbacks: list[str]) -> tuple[list[tuple[int, str]], list[str]]:
        """
        Filters whole reviews into actionable and non-actionable.
        Returns (actionable, non_actionable_texts). Each actionable entry is
        (source_id, text), with source_id the 1-based index in the input list.
        """
        chunks = [feedbacks[i:i + SIFT_CHUNK_SIZE] for i in range(0, len(feedbacks), SIFT_CHUNK_SIZE)]
        tasks = [self._sift_chunk(chunk, global_offset=i * SIFT_CHUNK_SIZE) for i, chunk in enumerate(chunks)]
        chunk_results = await asyncio.gather(*tasks)

        actionable: list[tuple[int, str]] = []
        non_actionable: list[str] = []
        for a, na, _decided in chunk_results:
            actionable.extend(a)
            non_actionable.extend(na)
        return actionable, non_actionable

    async def _sift_chunk(self, chunk: list[str], global_offset: int) -> tuple[list[tuple[int, str]], list[str], bool]:
        """
        Sift a single chunk of feedbacks. IDs in the prompt are local (1-based);
        results are mapped back using global_offset.
        The third value is False when the call or the parse failed and every
        review in the chunk was kept without a model decision.
        """
        numbered = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(chunk))
        prompt = f"""You are filtering product feedback for a PM. Return ONLY a JSON array of IDs (integers) for feedbacks that are actionable — meaning they contain a specific bug, feature request, UX issue, or reproducible problem. Exclude: generic praise ("great app"), gibberish, off-topic content, or vague emotional reactions with no product signal.

FEEDBACKS:
{numbered}

Return ONLY valid JSON array of integers, e.g.: [1, 3, 5]"""

        import logging as _logging
        try:
            text, _ = await self._call_llm(
                prompt, max_tokens=500, cerebras_model=CEREBRAS_STRUCTURED_MODEL, prefer_cerebras=True,
            )
        except Exception as e:
            _logging.getLogger("triage").warning("_sift_chunk(offset=%d): call failed, treating all as actionable. Error: %s", global_offset, e)
            return [(global_offset + i, f) for i, f in enumerate(chunk, 1)], [], False

        try:
            clean = re.sub(r"```(?:json)?\s*\n?", "", text)
            clean = re.sub(r"\n?```", "", clean).strip()
            m = re.search(r'\[[\d,\s]*\]', clean)
            actionable_ids = set(json.loads(m.group(0) if m else clean))
        except Exception:
            _logging.getLogger("triage").warning("_sift_chunk(offset=%d): parse failed, treating all as actionable. Raw: %s", global_offset, text[:200])
            return [(global_offset + i, f) for i, f in enumerate(chunk, 1)], [], False

        actionable = [(global_offset + i, f) for i, f in enumerate(chunk, 1) if i in actionable_ids]
        non_actionable = [f for i, f in enumerate(chunk, 1) if i not in actionable_ids]
        return actionable, non_actionable, True

    # ------------------------------------------------------------------
    # Echo — LLM-based clustering
    # ------------------------------------------------------------------

    async def cluster_with_llm(self, items: list[dict]) -> list[dict]:
        """
        Merges elements that name the same shippable action.
        A generic label such as Other is split back into one ticket per action.
        score is the number of elements in the cluster. Ticket order is RICE, on the cards.
        Each cluster dict: {score, cluster_label, category, items}.
        Tags each item with cluster_id and cluster_label.
        """
        if not items:
            return []
        id_action_list = "\n".join(f"{it['id']}: {it.get('action', '')}" for it in items)
        prompt = f"""You are a product analyst. Group these action names. Each line is one shippable action already named by an earlier step. Put names that refer to the same change in the same group, including a group of one. Two different changes stay apart. Use every id exactly once.

ACTIONS (id: action):
{id_action_list}

cluster_label is the action itself, at most 8 words. Use the clearest wording already in the group.
Never label a group Other, Misc, Uncategorized, Bugs, or any theme broader than the action.

YOUR RESPONSE MUST START WITH [ AND CONTAIN ONLY A VALID JSON ARRAY. No explanation, no preamble, no markdown.
[
  {{
    "cluster_label": "the action name",
    "ids": [1, 3, 7]
  }}
]"""

        text, _ = await self._call_llm(
            prompt, max_tokens=2000, cerebras_model=CEREBRAS_STRUCTURED_MODEL, prefer_cerebras=True,
        )
        try:
            # Strip <think> blocks, fences, then find the JSON array
            clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            clean = re.sub(r"```(?:json)?\s*\n?", "", clean)
            clean = re.sub(r"\n?```", "", clean).strip()
            # Find the first [ ... ] block (may have preamble text before it)
            m = re.search(r'\[[\s\S]*\]', clean)
            raw_clusters = json.loads(m.group(0) if m else clean)
        except Exception as e:
            raise RuntimeError(f"cluster_with_llm: failed to parse LLM response: {e}\nRaw: {text[:300]}")

        # Build id → item lookup
        item_by_id: dict[int, dict] = {it["id"]: it for it in items}

        result = []
        assigned_ids: set[int] = set()
        for raw in raw_clusters:
            cluster_ids = []
            for element_id in raw.get("ids", []):
                if element_id in item_by_id and element_id not in assigned_ids and element_id not in cluster_ids:
                    cluster_ids.append(element_id)
            if not cluster_ids:
                continue
            cluster_items = [item_by_id[i] for i in cluster_ids]
            assigned_ids.update(cluster_ids)
            score = len(cluster_items)
            cats = [it.get("category", "") for it in cluster_items]
            majority_cat = max(set(cats), key=cats.count)
            result.append({
                "score": score,
                "cluster_label": raw.get("cluster_label", "Uncategorized"),
                "category": majority_cat,
                "items": cluster_items,
            })

        # An element the model forgot must not be glued to a different action.
        for item in items:
            if item["id"] in assigned_ids:
                continue
            result.append({
                "score": 1,
                "cluster_label": item.get("action") or item.get("summary") or "Untitled",
                "category": item.get("category") or "Other",
                "items": [item],
            })

        result = settle_clusters(result)
        result.sort(key=lambda x: x["score"], reverse=True)

        # Tag each item with cluster_id and cluster_label
        for cluster_id, cluster in enumerate(result):
            for item in cluster["items"]:
                item["cluster_id"] = cluster_id
                item["cluster_label"] = cluster["cluster_label"]

        return result

    # ------------------------------------------------------------------
    # Step 1: Categorization + Self-validation (single LLM call)
    # ------------------------------------------------------------------

    async def categorize_and_validate(
        self, feedbacks: list[tuple[int, str]]
    ) -> tuple[list[dict], list[dict], list[dict], str | None]:
        """
        Splits each kept review into verbatim elements and names a shippable action.
        Elements without that name are returned as unclear and do not continue.
        Returns (elements, unclear, corrections_list, fallback_provider).
        """
        return await self._categorize_chunked(feedbacks, GROQ_CHUNK_SIZE)

    async def generate_user_stories(
        self, clusters: list[dict], actions: list[str]
    ) -> tuple[list[dict], str | None]:
        """
        One sprint card per cluster. The action title is the cluster label.
        Each supporting quote is the element's excerpt, not the whole review.
        Reach is the number of elements in the cluster.
        Cards are sorted by RICE score descending.
        Returns (cards, fallback_provider).
        """
        def _norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

        def _parse_card(text: str) -> dict | None:
            clean = re.sub(r"```(?:json)?\s*\n?", "", text)
            clean = re.sub(r"\n?```", "", clean).strip()
            try:
                parsed = json.loads(clean)
            except Exception:
                m = re.search(r"\{[\s\S]*\}", clean)
                if not m:
                    return None
                try:
                    parsed = json.loads(m.group(0))
                except Exception:
                    return None
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else None
            return parsed if isinstance(parsed, dict) else None

        def _attach_feedbacks(card: dict, items: list[dict], action: str) -> dict:
            model_fbs = [fb for fb in (card.get("feedbacks") or []) if isinstance(fb, dict)]
            by_index = len(model_fbs) == len(items)
            by_norm: dict[str, str] = {}
            for fb in model_fbs:
                tr = fb.get("translation")
                text = fb.get("text") or ""
                if tr and _norm(tr) != _norm(text):
                    by_norm[_norm(text)] = tr
            rebuilt = []
            for i, it in enumerate(items):
                excerpt = it.get("excerpt") or ""
                entry: dict = {"text": excerpt}
                if it.get("source_id") is not None:
                    entry["source_id"] = it["source_id"]
                tr = None
                if by_index:
                    raw = model_fbs[i].get("translation")
                    quoted = model_fbs[i].get("text") or ""
                    if raw and _norm(raw) != _norm(excerpt) and _norm(raw) != _norm(quoted):
                        tr = raw
                if tr is None:
                    tr = by_norm.get(_norm(excerpt))
                if tr:
                    entry["translation"] = tr
                rebuilt.append(entry)
            card["feedbacks"] = rebuilt
            card["action"] = action
            rice = card.get("rice")
            if not isinstance(rice, dict):
                rice = {}
                card["rice"] = rice
            rice["reach"] = len(items)
            return card

        async def one(index: int, action: str) -> tuple[dict | None, str | None]:
            items = clusters[index]["items"] if index < len(clusters) else []
            feedbacks = [
                {
                    "source_id": it.get("source_id"),
                    "excerpt": it.get("excerpt", ""),
                    "summary": it.get("summary", ""),
                }
                for it in items
            ]
            prompt = f"""You are a senior Product Manager writing one actionable sprint card.

ACTION (copy this title verbatim into the "action" field):
{action}

ACTIONABLE EXCERPTS for this action, in order. There are {len(feedbacks)}. Each excerpt is already only the part of a review that asks for this action. Include every one. Do not quote the rest of the review.
{json.dumps(feedbacks, ensure_ascii=False, indent=2)}

Follow these steps:

STEP 1 — Detect action_type: "bug" | "performance" | "feature" | "ux" | "pricing" | "ai_quality" | "other"
  Use "ai_quality" when the action addresses the quality, tone, accuracy, or relevance of AI-generated responses.

STEP 2 — Copy EVERY excerpt above into "feedbacks", in the same order.
"text" is the excerpt, verbatim. "source_id" is the integer given with that excerpt. Copy both.
Do not drop, merge, or shorten an excerpt, and do not add sentences from the rest of the review.
For each excerpt, detect its language. If it is NOT English, add a "translation" field
with a concise English translation. If it IS English, omit the "translation" field entirely.

STEP 3 — Estimate RICE:
- reach: {len(feedbacks)}. This count is fixed. Copy it. Do not estimate a different number.
- impact: how much this hurts each person who hits it. Use ONLY one of these values (Intercom's RICE scale):
  * 3    = massive (blocking, or they leave)
  * 2    = high
  * 1    = medium
  * 0.5  = low
  * 0.25 = minimal (cosmetic)
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
- ux, pricing, ai_quality, other → provide: problem, success_metric, next_step

Return ONLY one valid JSON object, no markdown, no surrounding text:
{{
  "action": "exact action title verbatim",
  "action_type": "bug",
  "feedbacks": [
    {{"text": "verbatim excerpt in original language", "source_id": 1, "translation": "English translation"}},
    {{"text": "verbatim English excerpt", "source_id": 2}}
  ],
  "rice": {{"reach": 12, "impact": 3, "confidence": 0.8, "effort_label": "M", "effort": 2, "score": 144}},
  "what_breaks": "Concise description of what fails and when",
  "done_when": "Observable, testable completion criteria",
  "next_step": "Concrete first engineering or design action"
}}"""
            text, provider = await self._call_llm(prompt, max_tokens=4000)
            card = _parse_card(text)
            if card is None:
                print(f"[generate_user_stories] parse error for {action!r}\nRaw output: {text[:500]}")
                return None, provider
            card = _attach_feedbacks(card, items, action)
            _normalize_rice(card)
            return card, provider

        results = await asyncio.gather(
            *[one(i, action) for i, action in enumerate(actions)],
            return_exceptions=True,
        )
        cards: list[dict] = []
        fallback_provider: str | None = None
        for result in results:
            if isinstance(result, Exception):
                print(f"[generate_user_stories] card failed: {result}")
                continue
            card, provider = result
            if provider and fallback_provider is None:
                fallback_provider = provider
            if card:
                cards.append(card)
        cards.sort(key=lambda c: c.get("rice", {}).get("score", 0), reverse=True)
        return cards, fallback_provider

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
