"""Turn a kept review into verbatim actionable excerpts.

An excerpt must be a span of the source review. A paraphrase is rejected.
"""

from __future__ import annotations

import logging
import re

_log = logging.getLogger("triage")

# One-to-one, so a match index in the folded string is the same index in the source.
_FOLD = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u00a0": " ",
})


def locate_excerpt(original: str, excerpt: str) -> str | None:
    """Return the source slice the excerpt points at, or None if it is not in the review."""
    if not original or not excerpt:
        return None
    excerpt = excerpt.strip()
    if len(excerpt) >= 2 and excerpt[0] == excerpt[-1] and excerpt[0] in "\"'“”‘’":
        excerpt = excerpt[1:-1].strip()
    if not excerpt:
        return None
    at = original.find(excerpt)
    if at != -1:
        return original[at:at + len(excerpt)]
    folded_original = original.translate(_FOLD)
    folded_excerpt = excerpt.translate(_FOLD)
    parts = [part for part in re.split(r"\s+", folded_excerpt) if part]
    if not parts:
        return None
    pattern = r"\s+".join(re.escape(part) for part in parts)
    match = re.search(pattern, folded_original)
    if not match:
        return None
    return original[match.start():match.end()]


_GENERIC_ACTIONS = {
    "other",
    "others",
    "misc",
    "miscellaneous",
    "uncategorized",
    "general",
    "various",
    "mixed",
    "unclear",
    "untitled",
    "n a",
    "na",
    "bugs",
    "bug",
    "feedback",
    "feedbacks",
    "improvements",
    "improvement",
    "fix bugs",
    "fix bug",
    "various bugs",
    "general feedback",
    "mixed feedback",
    "heterogeneous",
    "issues",
    "various issues",
    "improve the app",
    "app improvements",
    "none",
    "tbd",
    "todo",
    "fix",
    "improve",
    "update",
    "change",
    "issue",
    "problem",
}


def action_key(action: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (action or "").lower()).strip()


def is_clear_action(action: str) -> bool:
    """An action is a shippable change. A theme such as Other is not."""
    key = action_key(action)
    if len(key) < 3:
        return False
    return key not in _GENERIC_ACTIONS


def settle_clusters(clusters: list[dict]) -> list[dict]:
    """Split a generic bucket so each Iris action name becomes its own ticket."""
    settled: list[dict] = []
    for cluster in clusters:
        label = str(cluster.get("cluster_label") or "")
        items = [item for item in cluster.get("items") or [] if isinstance(item, dict)]
        if is_clear_action(label):
            settled.append({**cluster, "items": items, "score": len(items)})
            continue
        groups: dict[str, list[dict]] = {}
        order: list[str] = []
        for item in items:
            action = str(item.get("action") or "").strip()
            if not is_clear_action(action):
                continue
            key = action_key(action)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(item)
        for key in order:
            members = groups[key]
            categories = [member.get("category") or "" for member in members]
            majority = max(set(categories), key=categories.count) if categories else "Other"
            settled.append({
                "score": len(members),
                "cluster_label": str(members[0].get("action") or "").strip(),
                "category": majority,
                "items": members,
            })
    return settled


def accept_elements(
    chunk: list[tuple[int, str]],
    data: dict,
    categories: set[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Keep elements whose excerpt is real and whose action is a shippable change.

    Elements without a clear action go to the unclear list and do not continue.
    `_local_id` is the id Iris used inside this chunk. The caller remaps it.
    """
    by_source = {source_id: text for source_id, text in chunk}
    raw = data.get("elements")
    if not isinstance(raw, list):
        raw = []

    kept: list[dict] = []
    unclear: list[dict] = []
    seen: set[tuple[int, str]] = set()

    def remember_unclear(source_id: int, original: str, excerpt: str, reason: str) -> None:
        key = (source_id, excerpt)
        if key in seen:
            return
        seen.add(key)
        unclear.append({
            "source_id": source_id,
            "original": original,
            "excerpt": excerpt,
            "reason": reason[:120],
        })

    for element in raw:
        if not isinstance(element, dict):
            continue
        try:
            source_id = int(element.get("source_id"))
        except (TypeError, ValueError):
            continue
        original = by_source.get(source_id)
        if original is None:
            _log.warning("Iris element rejected: source_id %s is not in this chunk", element.get("source_id"))
            continue
        excerpt = locate_excerpt(original, str(element.get("excerpt") or ""))
        if excerpt is None:
            _log.warning("Iris excerpt rejected for feedback %s: not a span of the review", source_id)
            continue
        key = (source_id, excerpt)
        if key in seen:
            continue
        action = str(element.get("action") or "").strip()
        if not is_clear_action(action):
            remember_unclear(source_id, original, excerpt, "no clear action")
            continue
        seen.add(key)
        try:
            local_id = int(element.get("id"))
        except (TypeError, ValueError):
            local_id = None
        category = element.get("category") or "Other"
        if category not in categories:
            category = "Other"
        kept.append({
            "_local_id": local_id,
            "source_id": source_id,
            "original": original,
            "excerpt": excerpt,
            "summary": str(element.get("summary") or "").strip(),
            "action": action,
            "category": category,
        })

    for entry in data.get("unclear") or []:
        if not isinstance(entry, dict):
            continue
        try:
            source_id = int(entry.get("source_id"))
        except (TypeError, ValueError):
            continue
        original = by_source.get(source_id)
        if original is None:
            continue
        excerpt = locate_excerpt(original, str(entry.get("excerpt") or ""))
        if excerpt is None:
            _log.warning("Iris unclear excerpt rejected for feedback %s", source_id)
            continue
        reason = str(entry.get("reason") or "no clear action").strip() or "no clear action"
        remember_unclear(source_id, original, excerpt, reason)

    known_ids = {item["_local_id"] for item in kept if item["_local_id"] is not None}
    corrections: list[dict] = []
    for correction in data.get("corrections") or []:
        if not isinstance(correction, dict):
            continue
        if correction.get("old_value") == correction.get("new_value"):
            continue
        try:
            local_id = int(correction.get("id"))
        except (TypeError, ValueError):
            continue
        if local_id not in known_ids:
            continue
        corrections.append({**correction, "id": local_id, "_local_id": local_id})
    return kept, unclear, corrections
