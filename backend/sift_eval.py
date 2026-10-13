"""Score Sift against a frozen, human-labeled review set.

Recall is the share of truly actionable reviews that Sift kept.
Precision is the share of kept reviews that are truly actionable.
A chunk that failed open is excluded from both rates, and it blocks a pass.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CONTRACT_SIZE = 200
RECALL_MIN = 0.95
PRECISION_MIN = 0.90
CHUNK_SIZE = 25

_GOLDEN_PATH = Path(__file__).resolve().parent / "eval" / "sift_golden.json"


def load_golden(path: Path | None = None) -> dict:
    data = json.loads((path or _GOLDEN_PATH).read_text(encoding="utf-8"))
    items = data.get("items") or []
    if [item.get("id") for item in items] != list(range(1, len(items) + 1)):
        raise ValueError("Sift golden ids must be 1..n in file order")
    return {
        "version": data.get("version") or "unversioned",
        "items": items,
    }


def score_sift(
    items: list[dict],
    predicted_ids: set[int],
    failed_ids: set[int],
    failed_chunks: list[dict],
    version: str,
) -> dict:
    """Score one run. failed_ids are reviews whose chunk did not decide."""
    judged = [item for item in items if item["id"] not in failed_ids]
    missed = [
        item for item in judged
        if item["actionable"] and item["id"] not in predicted_ids
    ]
    kept_by_mistake = [
        item for item in judged
        if not item["actionable"] and item["id"] in predicted_ids
    ]
    true_kept = [
        item for item in judged
        if item["actionable"] and item["id"] in predicted_ids
    ]
    actionable_total = len(true_kept) + len(missed)
    kept_total = len(true_kept) + len(kept_by_mistake)
    recall = (len(true_kept) / actionable_total) if actionable_total else None
    precision = (len(true_kept) / kept_total) if kept_total else None

    reasons: list[str] = []
    if len(items) != CONTRACT_SIZE:
        reasons.append(f"This set has {len(items)} of the {CONTRACT_SIZE} reviews required for the contract.")
    if failed_chunks:
        reasons.append("A chunk did not answer, so the run cannot pass.")
    if recall is None:
        reasons.append("Recall is undefined: the decided reviews include no actionable case.")
    elif recall < RECALL_MIN:
        reasons.append(f"Recall {recall:.0%} is below {RECALL_MIN:.0%}.")
    if precision is None:
        reasons.append("Precision is undefined: Sift kept none of the decided reviews.")
    elif precision < PRECISION_MIN:
        reasons.append(f"Precision {precision:.0%} is below {PRECISION_MIN:.0%}.")

    passed = not reasons
    return {
        "version": version,
        "contract_size": CONTRACT_SIZE,
        "recall_min": RECALL_MIN,
        "precision_min": PRECISION_MIN,
        "item_count": len(items),
        "actionable_count": sum(1 for item in items if item["actionable"]),
        "chunk_count": (len(items) + CHUNK_SIZE - 1) // CHUNK_SIZE if items else 0,
        "failed_chunks": failed_chunks,
        "recall": recall,
        "precision": precision,
        "recall_hits": len(true_kept),
        "recall_total": actionable_total,
        "precision_hits": len(true_kept),
        "precision_total": kept_total,
        "passed": passed,
        "reasons": reasons,
        "missed": [_public_item(item) for item in missed],
        "kept_by_mistake": [_public_item(item) for item in kept_by_mistake],
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }


def _public_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "text": item["text"],
        "actionable": bool(item["actionable"]),
        "reason": item.get("reason") or "",
    }
