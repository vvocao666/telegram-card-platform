from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


PUBG_CARD_RE = re.compile(
    r"(?<![A-Z0-9])S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}(?![A-Z0-9])"
)
PUBG_PREFIX_RE = re.compile(r"(?<![A-Z0-9])S07[0-9]{3}(?![0-9])")
SUSPICIOUS_PUBG_PREFIX_RE = re.compile(r"(?<![A-Z0-9])50[0-9]{4}(?![0-9])")


@dataclass(frozen=True)
class CpuReviewDecision:
    review_required: bool
    reasons: tuple[str, ...]


def assess_cpu_review_risk(
    best: dict[str, Any],
    original: dict[str, Any],
    enhanced: dict[str, Any],
    *,
    line_recoveries: list[dict[str, str]] | None = None,
    image_metrics: dict[str, Any] | None = None,
    low_confidence: float = 0.90,
    variant_conflict_resolved: bool = False,
) -> CpuReviewDecision:
    """Classify only evidence risks; never rewrite or infer a card."""
    reasons: list[str] = []
    best_cards = _card_set(best)
    marker_count = _marker_slot_count(best)

    if marker_count and not best_cards:
        reasons.append("pubg_marker_without_valid_card")
    elif marker_count > len(best_cards):
        reasons.append("pubg_marker_count_mismatch")

    original_cards = _card_set(original)
    enhanced_cards = _card_set(enhanced)
    if (
        original_cards
        and enhanced_cards
        and original_cards != enhanced_cards
        and not variant_conflict_resolved
    ):
        reasons.append("gpu_variant_conflict")

    valid_scores = [
        float(item.get("score", 0.0))
        for item in best.get("cards", [])
        if isinstance(item, dict) and PUBG_CARD_RE.fullmatch(str(item.get("text", "")).upper())
    ]
    if valid_scores and min(valid_scores) < low_confidence:
        reasons.append("low_card_confidence")

    if line_recoveries:
        reasons.append("line_roi_recovery")

    metrics = image_metrics or {}
    width = int(metrics.get("width", 0) or 0)
    height = int(metrics.get("height", 0) or 0)
    if marker_count and height > 0 and width / height >= 3.0:
        reasons.append("thin_strip_pubg")

    return CpuReviewDecision(bool(reasons), tuple(dict.fromkeys(reasons)))


def _card_set(result: dict[str, Any]) -> set[str]:
    cards: set[str] = set()
    for item in result.get("cards", []) or []:
        value = str(item.get("text", "") if isinstance(item, dict) else item).upper()
        if PUBG_CARD_RE.fullmatch(value):
            cards.add(value)
    return cards


def _marker_slot_count(result: dict[str, Any]) -> int:
    full_cards: set[str] = set()
    partial_slots = 0
    for item in result.get("texts", []) or []:
        text = str(item.get("text", "") if isinstance(item, dict) else item).upper()
        cards = set(PUBG_CARD_RE.findall(text))
        if cards:
            full_cards.update(cards)
            continue
        partial_slots += len(PUBG_PREFIX_RE.findall(text))
        partial_slots += len(SUSPICIOUS_PUBG_PREFIX_RE.findall(text))
    return len(full_cards) + partial_slots
