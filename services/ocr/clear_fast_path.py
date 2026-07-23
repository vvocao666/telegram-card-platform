from __future__ import annotations

import re
from typing import Any


MIN_CONFIRMATION_SCORE = 0.985
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
    if bool(getattr(result, "has_unresolved_pubg_fragment", False)):
        return None
    if bool(getattr(result, "remote_variant_conflict", False)):
        return None
    expected_count = getattr(result, "pubg_expected_count", None)
    if expected_count not in (None, 1):
        return None

    card = cards[0]
    if not PUBG_CARD_RE.fullmatch(card):
        return None
    if not _high_score_exact(result, "remote_original_card_scores", card):
        return None
    if not _high_score_exact(result, "remote_enhanced_card_scores", card):
        return None
    cpu_candidates = tuple(
        str(candidate).upper()
        for candidate in (getattr(result, "remote_cpu_candidates", ()) or ())
    )
    if cpu_candidates != (card,):
        return None
    return card


def _high_score_exact(result: Any, attribute: str, card: str) -> bool:
    candidates = tuple(getattr(result, attribute, ()) or ())
    if len(candidates) != 1:
        return False
    candidate, score = candidates[0]
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return False
    return str(candidate).upper() == card and numeric_score >= MIN_CONFIRMATION_SCORE
