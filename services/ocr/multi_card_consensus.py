from __future__ import annotations

import re
from typing import Any


PUBG_CARD_RE = re.compile(
    r"^S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}$"
)
MIN_VARIANT_SCORE = 0.97
MIN_SECONDARY_VARIANT_SCORE = 0.95


def complete_dual_variant_multi_card_consensus(
    remote: Any,
) -> tuple[str, ...] | None:
    """Accept complete multi-card output only when both GPU variants agree exactly."""
    remote_cards = _cards(remote)
    if len(remote_cards) < 2:
        return None
    if getattr(remote, "psn_cards", ()):
        return None
    if getattr(remote, "uncertain_count", 0):
        return None
    if getattr(remote, "remote_variant_conflict", False):
        return None
    expected = getattr(remote, "pubg_expected_count", None)
    if expected != len(remote_cards):
        return None
    if not all(PUBG_CARD_RE.fullmatch(card) for card in remote_cards):
        return None

    original_values = getattr(remote, "remote_original_rebuilt_card_scores", ()) or ()
    enhanced_values = getattr(remote, "remote_enhanced_rebuilt_card_scores", ()) or ()
    if _scored_cards(remote, "remote_original_rebuilt_card_scores") != remote_cards:
        return None
    if _scored_cards(remote, "remote_enhanced_rebuilt_card_scores") != remote_cards:
        return None
    if not _paired_variant_scores_are_high(original_values, enhanced_values):
        return None

    cpu_cards = tuple(
        str(card).upper()
        for card in (getattr(remote, "remote_cpu_candidates", ()) or ())
    )
    if cpu_cards and not _is_exact_ordered_subset(remote_cards, cpu_cards):
        return None
    cpu_reasons = set(getattr(remote, "remote_cpu_review_reasons", ()) or ())
    if cpu_reasons - {
        "pubg_marker_count_mismatch",
        "pubg_marker_without_valid_card",
    }:
        return None
    return remote_cards


def dual_variant_multi_card_consensus(
    remote: Any,
    cloud: Any,
) -> tuple[str, ...] | None:
    """Confirm multi-card GPU output only with exact high-confidence dual variants."""
    remote_cards = _cards(remote)
    cloud_cards = _cards(cloud)
    if len(remote_cards) < 2 or not 2 <= len(cloud_cards) <= len(remote_cards):
        return None
    if getattr(remote, "psn_cards", ()) or getattr(cloud, "psn_cards", ()):
        return None
    if getattr(remote, "uncertain_count", 0) or getattr(cloud, "uncertain_count", 0):
        return None
    cpu_cards = tuple(
        str(card).upper()
        for card in (getattr(remote, "remote_cpu_candidates", ()) or ())
    )
    if cpu_cards and not _is_exact_ordered_subset(remote_cards, cpu_cards):
        return None
    cpu_reasons = set(getattr(remote, "remote_cpu_review_reasons", ()) or ())
    if cpu_reasons - {"pubg_marker_count_mismatch"}:
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
    if not _is_ordered_cloud_subset(remote_cards, cloud_cards):
        return None
    return remote_cards


def cloud_completes_one_rejected_remote_slot(
    remote: Any,
    cloud: Any,
) -> tuple[str, ...] | None:
    """Accept one cloud-completed slot only with repeated, traceable evidence.

    This covers multi-card images where Remote reconstructs every slot but one
    candidate is rejected by the PUBG body validator.  OCR.space must read the
    missing valid card at least twice, while a high-confidence Remote variant
    anchors the same prefix and first two body groups with only one differing
    character.  No character is corrected or guessed here.
    """
    remote_cards = _cards(remote)
    cloud_cards = _cards(cloud)
    expected = getattr(remote, "pubg_expected_count", None)
    if (
        len(remote_cards) < 2
        or len(cloud_cards) != len(remote_cards) + 1
        or expected != len(cloud_cards)
        or getattr(remote, "psn_cards", ())
        or getattr(cloud, "psn_cards", ())
        or getattr(cloud, "uncertain_count", 0)
        or not all(PUBG_CARD_RE.fullmatch(card) for card in remote_cards + cloud_cards)
        or any(_has_forbidden_body_chars(card) for card in cloud_cards)
        or not _is_exact_ordered_subset(cloud_cards, remote_cards)
    ):
        return None

    missing = tuple(card for card in cloud_cards if card not in remote_cards)
    if len(missing) != 1:
        return None
    confirmed = missing[0]
    raw_cloud_cards = [
        line.strip()
        for line in str(getattr(cloud, "raw_text", "") or "").upper().splitlines()
        if PUBG_CARD_RE.fullmatch(line.strip())
    ]
    if raw_cloud_cards.count(confirmed) < 2:
        return None

    variant_values = tuple(
        (str(card).upper(), float(score))
        for attribute in (
            "remote_original_rebuilt_card_scores",
            "remote_enhanced_rebuilt_card_scores",
        )
        for card, score in (getattr(remote, attribute, ()) or ())
    )
    anchored = [
        card
        for card, score in variant_values
        if score >= MIN_VARIANT_SCORE
        and _same_slot_prefix(card, confirmed)
        and _compact_hamming(card, confirmed) == 1
        and _has_forbidden_body_chars(card)
    ]
    if not anchored:
        return None
    return cloud_cards


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


def _paired_variant_scores_are_high(
    original_values: tuple[tuple[str, float], ...],
    enhanced_values: tuple[tuple[str, float], ...],
) -> bool:
    if not original_values or len(original_values) != len(enhanced_values):
        return False
    for original, enhanced in zip(original_values, enhanced_values):
        original_score = float(original[1])
        enhanced_score = float(enhanced[1])
        if min(original_score, enhanced_score) < MIN_SECONDARY_VARIANT_SCORE:
            return False
        if max(original_score, enhanced_score) < MIN_VARIANT_SCORE:
            return False
    return True


def _compact_hamming(left: str, right: str) -> int:
    left_compact = left.replace("-", "")
    right_compact = right.replace("-", "")
    if len(left_compact) != len(right_compact):
        return max(len(left_compact), len(right_compact))
    return sum(a != b for a, b in zip(left_compact, right_compact))


def _is_ordered_cloud_subset(
    remote_cards: tuple[str, ...],
    cloud_cards: tuple[str, ...],
) -> bool:
    remote_index = 0
    for cloud_card in cloud_cards:
        while (
            remote_index < len(remote_cards)
            and _compact_hamming(remote_cards[remote_index], cloud_card) > 1
        ):
            remote_index += 1
        if remote_index >= len(remote_cards):
            return False
        remote_index += 1
    return True


def _is_exact_ordered_subset(
    complete_cards: tuple[str, ...],
    partial_cards: tuple[str, ...],
) -> bool:
    complete_index = 0
    for partial_card in partial_cards:
        while (
            complete_index < len(complete_cards)
            and complete_cards[complete_index] != partial_card
        ):
            complete_index += 1
        if complete_index >= len(complete_cards):
            return False
        complete_index += 1
    return True


def _same_slot_prefix(left: str, right: str) -> bool:
    left_parts = left.split("-")
    right_parts = right.split("-")
    return (
        len(left_parts) == 4
        and len(right_parts) == 4
        and left_parts[:3] == right_parts[:3]
    )


def _has_forbidden_body_chars(card: str) -> bool:
    parts = card.split("-", 1)
    return len(parts) == 2 and any(char in "01OI" for char in parts[1].replace("-", ""))
