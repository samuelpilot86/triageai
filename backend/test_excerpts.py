"""Checks that an excerpt must be a real span of its source review."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from excerpts import accept_elements, is_clear_action, locate_excerpt, settle_clusters

CATEGORIES = {
    "Bug / Error",
    "Feature Request",
    "UX / Usability",
    "Performance",
    "Pricing",
    "Onboarding / Documentation",
    "Customer Support",
    "Security / Privacy",
    "Other",
}

REVIEW = (
    "It makes great images but the filter flags tea as sexual. "
    "Also a failed generation now counts as one of your daily credits."
)


def test_exact_span():
    assert locate_excerpt(REVIEW, "the filter flags tea as sexual.") == "the filter flags tea as sexual."


def test_whitespace_folds_back_to_the_source():
    source = "the filter flags\ntea as sexual"
    assert locate_excerpt(source, "the filter flags tea as sexual") == source


def test_curly_apostrophe_maps_back_to_the_source():
    source = "it's a bug"
    assert locate_excerpt(source, "it’s a bug") == source


def test_wrapped_quotes_are_stripped_before_matching():
    assert locate_excerpt(REVIEW, '"the filter flags tea as sexual."') == "the filter flags tea as sexual."


def test_paraphrase_is_rejected():
    assert locate_excerpt(REVIEW, "moderation is too aggressive") is None


def test_non_contiguous_join_is_rejected():
    joined = "the filter flags tea as sexual. a failed generation now counts"
    assert locate_excerpt(REVIEW, joined) is None


def test_one_review_becomes_two_elements_and_a_bad_excerpt_is_dropped():
    chunk = [(12, REVIEW)]
    data = {
        "elements": [
            {
                "id": 1,
                "source_id": 12,
                "excerpt": "the filter flags tea as sexual.",
                "summary": "Filter flags tea",
                "action": "Stop flagging tea as sexual",
                "category": "Bug / Error",
            },
            {
                "id": 2,
                "source_id": 12,
                "excerpt": "a failed generation now counts as one of your daily credits.",
                "summary": "Failed generation spends a credit",
                "action": "Stop charging a credit for a failed generation",
                "category": "Pricing",
            },
            {
                "id": 3,
                "source_id": 12,
                "excerpt": "the filter flags tea as sexual.",
                "summary": "duplicate",
                "action": "Stop flagging tea as sexual",
                "category": "Bug / Error",
            },
            {
                "id": 4,
                "source_id": 12,
                "excerpt": "moderation is too aggressive",
                "summary": "paraphrase",
                "category": "Bug / Error",
            },
            {
                "id": 5,
                "source_id": 99,
                "excerpt": "the filter flags tea as sexual.",
                "summary": "wrong source",
                "action": "Stop flagging tea as sexual",
                "category": "Bug / Error",
            },
            {
                "id": 6,
                "source_id": 12,
                "excerpt": "It makes great images",
                "summary": "Praise",
                "action": "Other",
                "category": "Other",
            },
        ],
        "unclear": [
            {
                "source_id": 12,
                "excerpt": "some bugs to fix",
                "reason": "not in the review",
            },
        ],
        "corrections": [
            {"id": 2, "field": "category", "old_value": "Bug / Error", "new_value": "Pricing", "reason": "billing"},
            {"id": 4, "field": "category", "old_value": "Other", "new_value": "Bug / Error", "reason": "dropped element"},
            {"id": 1, "field": "category", "old_value": "Bug / Error", "new_value": "Bug / Error", "reason": "same"},
        ],
    }
    elements, unclear, corrections = accept_elements(chunk, data, CATEGORIES)
    assert [element["excerpt"] for element in elements] == [
        "the filter flags tea as sexual.",
        "a failed generation now counts as one of your daily credits.",
    ]
    assert elements[0]["source_id"] == 12
    assert elements[0]["original"] == REVIEW
    assert [correction["id"] for correction in corrections] == [2]
    assert [item["excerpt"] for item in unclear] == ["It makes great images"]
    assert unclear[0]["reason"] == "no clear action"


def test_unknown_category_becomes_other():
    chunk = [(1, "The app crashes on launch.")]
    data = {
        "elements": [{
            "id": 1,
            "source_id": 1,
            "excerpt": "The app crashes on launch.",
            "summary": "Crashes on launch",
            "action": "Fix the crash on launch",
            "category": "Crash",
        }],
        "corrections": [],
    }
    elements, unclear, _ = accept_elements(chunk, data, CATEGORIES)
    assert elements[0]["category"] == "Other"
    assert unclear == []


def test_generic_bucket_splits_into_named_actions():
    settled = settle_clusters([{
        "cluster_label": "Other",
        "category": "Other",
        "items": [
            {"action": "Let users download question papers", "category": "Feature Request"},
            {"action": "Explain what LAP means", "category": "UX / Usability"},
            {"action": "Fix bugs", "category": "Bug / Error"},
        ],
    }])
    assert [cluster["cluster_label"] for cluster in settled] == [
        "Let users download question papers",
        "Explain what LAP means",
    ]


def test_a_named_cluster_stays_intact():
    settled = settle_clusters([{
        "cluster_label": "Fix incorrect math answers",
        "items": [{"action": "Correct wrong math answers", "category": "Bug / Error"}],
    }])
    assert settled[0]["cluster_label"] == "Fix incorrect math answers"


def test_vague_action_names_are_rejected():
    assert is_clear_action("Other") is False
    assert is_clear_action("Fix bugs") is False
    assert is_clear_action("Explain what LAP means") is True


if __name__ == "__main__":
    test_exact_span()
    test_whitespace_folds_back_to_the_source()
    test_curly_apostrophe_maps_back_to_the_source()
    test_wrapped_quotes_are_stripped_before_matching()
    test_paraphrase_is_rejected()
    test_non_contiguous_join_is_rejected()
    test_one_review_becomes_two_elements_and_a_bad_excerpt_is_dropped()
    test_unknown_category_becomes_other()
    test_generic_bucket_splits_into_named_actions()
    test_a_named_cluster_stays_intact()
    test_vague_action_names_are_rejected()
    print("ok")
