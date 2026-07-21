from __future__ import annotations

import sys
from pathlib import Path


WORKER_DIR = Path(__file__).resolve().parents[1] / "workers" / "rtx5070"
sys.path.insert(0, str(WORKER_DIR))

from cpu_review_policy import assess_cpu_review_risk


CARD = "S07336-Z483-CNEE-W6C5W"


def _result(cards, texts=None, score=0.99):
    return {
        "cards": [{"text": card, "score": score} for card in cards],
        "texts": texts or [{"text": card, "score": score} for card in cards],
    }


def test_clear_complete_card_is_low_risk():
    result = _result([CARD])
    decision = assess_cpu_review_risk(result, result, {"cards": [], "texts": []})
    assert decision.review_required is False


def test_duplicate_display_of_same_complete_card_is_low_risk():
    result = _result(
        [CARD],
        texts=[{"text": CARD, "score": 0.99}, {"text": CARD, "score": 0.99}],
    )
    decision = assess_cpu_review_risk(result, result, {"cards": [], "texts": []})
    assert decision.review_required is False


def test_incomplete_pubg_marker_is_high_risk():
    result = _result([], texts=[{"text": "S07336-Z483-CNEE-", "score": 0.99}])
    decision = assess_cpu_review_risk(result, result, {"cards": [], "texts": []})
    assert decision.review_required is True
    assert "pubg_marker_without_valid_card" in decision.reasons


def test_gpu_variant_conflict_is_high_risk():
    other = "S07336-Z483-CNEE-W6C5V"
    best = _result([CARD])
    decision = assess_cpu_review_risk(best, _result([CARD]), _result([other]))
    assert decision.review_required is True
    assert "gpu_variant_conflict" in decision.reasons


def test_low_card_confidence_is_high_risk():
    result = _result([CARD], score=0.75)
    decision = assess_cpu_review_risk(result, result, {"cards": [], "texts": []})
    assert decision.review_required is True
    assert "low_card_confidence" in decision.reasons


def test_thin_pubg_strip_is_high_risk_for_synchronous_cpu_review():
    result = _result([CARD])
    decision = assess_cpu_review_risk(
        result,
        result,
        {"cards": [], "texts": []},
        image_metrics={"width": 1280, "height": 225},
    )

    assert decision.review_required is True
    assert "thin_strip_pubg" in decision.reasons
