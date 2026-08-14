from __future__ import annotations

import re
from typing import Any


MIN_CONFIRMATION_SCORE = 0.985
MIN_SUPPORTING_SCORE = 0.97
MIN_CPU_CONFIRMATION_SCORE = 0.90
PUBG_CARD_RE = re.compile(r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}")


def confirmed_clear_remote_card(result: Any) -> str | None:
    """Return a card only when three independent observations agree exactly.

    The primary GPU original and enhanced passes must both produce the same
    high-confidence card, and the CPU OCR must independently produce that card.
    This function never normalizes, repairs, or creates a candidate.
    """

    cards = tuple(str(card).upper() for card in (getattr(result, "cards", ()) or ()))
    if len(cards) != 1 or getattr(result, "psn_cards", ()):
        return None
    if int(getattr(result, "uncertain_count", 0) or 0) != 0:
        return None
    if bool(getattr(result, "remote_variant_conflict", False)):
        return None
    expected_count = getattr(result, "pubg_expected_count", None)
    if expected_count not in (None, 1):
        return None

    card = cards[0]
    if not PUBG_CARD_RE.fullmatch(card):
        return None
    cpu_candidates = tuple(
        str(candidate).upper()
        for candidate in (getattr(result, "remote_cpu_candidates", ()) or ())
    )
    if cpu_candidates != (card,):
        return None
    if _resolved_gpu_cpu_variant_review(result, card):
        return card
    thin_strip_only_review = _thin_strip_only_cpu_review(result)
    if bool(getattr(result, "has_unresolved_pubg_fragment", False)) and not thin_strip_only_review:
        return None
    if thin_strip_only_review:
        if not _supporting_score_pair(result, card):
            return None
    elif not (
        _high_score_exact(result, "remote_original_card_scores", card)
        and _high_score_exact(result, "remote_enhanced_card_scores", card)
    ):
        return None
    return card


def _resolved_gpu_cpu_variant_review(result: Any, card: str) -> bool:
    """Accept a resolved one-slot GPU conflict only with exact CPU ROI support.

    The Worker has already selected one existing GPU candidate by rereading the
    original ROI.  This branch requires the independent CPU ROI to return that
    exact candidate at high confidence.  It never repairs or creates text.
    """

    if not bool(getattr(result, "remote_cpu_review_required", False)):
        return False
    reasons = set(getattr(result, "remote_cpu_review_reasons", ()) or ())
    if "gpu_variant_conflict" not in reasons or not reasons.issubset(
        {"gpu_variant_conflict", "thin_strip_pubg"}
    ):
        return False
    cpu_score = _exact_score(result, "remote_cpu_candidate_scores", card)
    if cpu_score is None or cpu_score < MIN_CPU_CONFIRMATION_SCORE:
        return False

    original = tuple(getattr(result, "remote_original_card_scores", ()) or ())
    enhanced = tuple(getattr(result, "remote_enhanced_card_scores", ()) or ())
    if len(original) != 1 or len(enhanced) != 1:
        return False
    original_card, original_score = original[0]
    enhanced_card, enhanced_score = enhanced[0]
    original_card = str(original_card).upper()
    enhanced_card = str(enhanced_card).upper()
    try:
        scores = (float(original_score), float(enhanced_score))
    except (TypeError, ValueError):
        return False
    if (
        card not in {original_card, enhanced_card}
        or original_card == enhanced_card
        or len(original_card) != len(enhanced_card)
        or sum(left != right for left, right in zip(original_card, enhanced_card)) != 1
    ):
        return False
    selected_score = scores[0] if original_card == card else scores[1]
    return min(scores) >= MIN_SUPPORTING_SCORE and selected_score >= MIN_CONFIRMATION_SCORE


def _high_score_exact(result: Any, attribute: str, card: str) -> bool:
    score = _exact_score(result, attribute, card)
    return score is not None and score >= MIN_CONFIRMATION_SCORE


def _exact_score(result: Any, attribute: str, card: str) -> float | None:
    candidates = tuple(getattr(result, attribute, ()) or ())
    if len(candidates) != 1:
        return None
    candidate, score = candidates[0]
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return None
    if str(candidate).upper() != card:
        return None
    return numeric_score


def _thin_strip_only_cpu_review(result: Any) -> bool:
    """Allow an exact three-source result past a shape-only review flag.

    ``thin_strip_pubg`` describes image geometry, not a character conflict.
    It is safe to clear only when it is the sole CPU review reason; all other
    risk signals keep the existing OCR.space/manual-review path.
    """

    if not bool(getattr(result, "remote_cpu_review_required", False)):
        return False
    reasons = tuple(
        str(reason)
        for reason in (getattr(result, "remote_cpu_review_reasons", ()) or ())
    )
    return reasons == ("thin_strip_pubg",)


def _supporting_score_pair(result: Any, card: str) -> bool:
    """Require two exact GPU reads, one strong and neither weak."""

    scores = (
        _exact_score(result, "remote_original_card_scores", card),
        _exact_score(result, "remote_enhanced_card_scores", card),
    )
    if any(score is None for score in scores):
        return False
    numeric_scores = tuple(float(score) for score in scores if score is not None)
    return min(numeric_scores) >= MIN_SUPPORTING_SCORE and max(numeric_scores) >= MIN_CONFIRMATION_SCORE
