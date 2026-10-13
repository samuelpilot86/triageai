"""Scorer for the Sift contract. No model call."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sift_eval import CONTRACT_SIZE, load_golden, score_sift


def _items(n: int, actionable_every: int = 1) -> list[dict]:
    return [
        {
            "id": i,
            "text": f"review {i}",
            "actionable": i % actionable_every == 0,
            "reason": "gold",
        }
        for i in range(1, n + 1)
    ]


def test_a_perfect_set_of_200_passes():
    items = _items(CONTRACT_SIZE, actionable_every=2)
    predicted = {item["id"] for item in items if item["actionable"]}
    result = score_sift(items, predicted, set(), [], version="v")
    assert result["passed"] is True
    assert result["recall"] == 1
    assert result["precision"] == 1
    assert result["reasons"] == []


def test_recall_below_95_percent_fails():
    items = _items(CONTRACT_SIZE, actionable_every=1)
    predicted = set(range(1, 190))  # 189 of 200 kept
    result = score_sift(items, predicted, set(), [], version="v")
    assert result["recall_hits"] == 189
    assert result["passed"] is False
    assert any("Recall" in reason for reason in result["reasons"])


def test_recall_of_exactly_95_percent_passes():
    items = _items(CONTRACT_SIZE, actionable_every=1)
    predicted = set(range(1, 191))  # 190 of 200
    result = score_sift(items, predicted, set(), [], version="v")
    assert result["recall"] == 0.95
    assert result["passed"] is True


def test_a_failed_chunk_is_not_counted_as_a_model_mistake_and_blocks_the_pass():
    items = _items(50, actionable_every=2)
    failed_ids = set(range(26, 51))
    predicted = {item["id"] for item in items if item["actionable"] or item["id"] in failed_ids}
    result = score_sift(
        items,
        predicted,
        failed_ids,
        [{"index": 2, "size": 25}],
        version="v",
    )
    assert result["kept_by_mistake"] == []
    assert result["precision"] == 1
    assert result["passed"] is False
    assert any("did not answer" in reason for reason in result["reasons"])


def test_a_short_set_cannot_pass_the_contract():
    items = _items(20, actionable_every=2)
    predicted = {item["id"] for item in items if item["actionable"]}
    result = score_sift(items, predicted, set(), [], version="sample-1")
    assert result["recall"] == 1
    assert result["passed"] is False
    assert any("20 of the 200" in reason for reason in result["reasons"])


def test_precision_is_undefined_when_nothing_was_kept():
    items = _items(CONTRACT_SIZE, actionable_every=2)
    result = score_sift(items, set(), set(), [], version="v")
    assert result["precision"] is None
    assert result["passed"] is False


def test_the_checked_in_sample_loads_in_order():
    golden = load_golden()
    assert golden["version"] == "sample-1"
    assert len(golden["items"]) == 20
    assert golden["items"][1]["actionable"] is True
    assert "crash" in golden["items"][1]["text"]


if __name__ == "__main__":
    test_a_perfect_set_of_200_passes()
    test_recall_below_95_percent_fails()
    test_recall_of_exactly_95_percent_passes()
    test_a_failed_chunk_is_not_counted_as_a_model_mistake_and_blocks_the_pass()
    test_a_short_set_cannot_pass_the_contract()
    test_precision_is_undefined_when_nothing_was_kept()
    test_the_checked_in_sample_loads_in_order()
    print("ok")
