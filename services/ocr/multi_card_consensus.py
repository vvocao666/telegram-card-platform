from __future__ import annotations

import re
from typing import Any


PUBG_CARD_RE = re.compile(
    r"^S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}$"
)
MIN_VARIANT_SCORE = 0.97


def dual_variant_multi_card_consensus(
    remote: Any,
    cloud: Any,
) -> tuple[str, ...] | None:
    """Confirm multi-card GPU output only with exact high-confidence dual variants."""
    remote_cards = _cards(remote)
    cloud_cards = _cards(cloud)
    if len(remote_cards) < 2 or len(cloud_cards) != len(remote_cards):
        return None
    if getattr(remote, "psn_cards", ()) or getattr(cloud, "psn_cards", ()):
        return None
    if getattr(cloud, "uncertain_count", 0):
        return None
    expected = getattr(remote, "pubg_expected_count", None)
    if expected is not None and expected != len(remote_cards):
        return None
    if not all(PUBG_CARD_RE.fullmatch(card) for card in remote_cards + cloud_cards):
        return None

    original = _scored_cards(remote, "remote_original_rebuilt_card_scores")
    enhanced = _scored_cards(remote, "remote_enhanced_rebuilt_card_scores")
    if original != remote_cards or enhanced != remote_cards:
        return None
    if not _scores_are_high(remote, "remote_original_rebuilt_card_scores"):
        return None
    if not _scores_are_high(remote, "remote_enhanced_rebuilt_card_scores"):
        return None
    if not all(
        _compact_hamming(remote_card, cloud_card) <= 1
        for remote_card, cloud_card in zip(remote_cards, cloud_cards)
    ):
        return None
    return remote_cards


def _cards(result: Any) -> tuple[str, ...]:
    return tuple(str(card).upper() for card in (getattr(result, "cards", ()) or ()))


def _scored_cards(result: Any, attribute: str) -> tuple[str, ...]:
    return tuple(
        str(card).upper()
        for card, _score in (getattr(result, attribute, ()) or ())
    )


def _scores_are_high(result: Any, attribute: str) -> bool:
    values = getattr(result, attribute, ()) or ()
    return bool(values) and all(float(score) >= MIN_VARIANT_SCORE for _card, score in values)


def _compact_hamming(left: str, right: str) -> int:
    left_compact = left.replace("-", "")
    right_compact = right.replace("-", "")
    if len(left_compact) != len(right_compact):
        return max(len(left_compact), len(right_compact))
    return sum(a != b for a, b in zip(left_compact, right_compact))
