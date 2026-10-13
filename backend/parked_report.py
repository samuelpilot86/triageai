"""
Penn executive report, parked out of the live pipeline.

Nothing in the running app imports this module. To put the report back,
call generate_report from analysis_stream and emit the "report" SSE event
again. The function still expects each feedback to carry priority
("High", "Medium" or "Low") and each cluster to carry score as a sum of
those weights. The live pipeline no longer produces those fields.
"""

import json
import re

import pandas as pd


async def generate_report(agent, items: list[dict], clusters: list[dict], app_name: str | None = None) -> tuple[str, list[str], str | None]:
    """
    Generates a PM executive report from the categorized feedbacks.
    clusters must be pre-computed before this call.
    Returns (report_text, actions, fallback_provider).
    """
    df = pd.DataFrame(items)
    priority_stats = df["priority"].value_counts().to_dict()

    # Build prompt context from top 6 clusters
    clusters_for_prompt = []
    for c in clusters[:6]:
        high_med = [it for it in c["items"] if it.get("priority") in ("High", "Medium")]
        verbatims = [it["original"][:200] for it in high_med]
        clusters_for_prompt.append({
            "priority_score": c["score"],
            "cluster_label": c.get("cluster_label", c.get("representative_summary", "")),
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
- cluster_label: short descriptive name for the cluster
- verbatims: real user quotes (original language) from High/Medium feedbacks in this cluster

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

    text, fallback_provider = await agent._call_llm(prompt, max_tokens=2500)
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
    return report_md, actions, fallback_provider
