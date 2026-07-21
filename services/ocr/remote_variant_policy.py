from __future__ import annotations

import re
from typing import Any


PUBG_CARD_RE = re.compile(r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}")


def remote_variants_conflict(payload: dict[str, Any]) -> bool:
    """原图与增强图都识别出卡密但内容不同时，要求备用 OCR 复核。"""
    original = _variant_cards(payload.get("ocr_original"))
    enhanced = _variant_cards(payload.get("ocr_enhanced"))
    review = payload.get("variant_review")
    if (
        isinstance(review, dict)
        and review.get("resolved") is True
        and str(review.get("selected_card", "")).upper() in (set(original) | set(enhanced))
        and str(review.get("review_card", "")).upper()
        == str(review.get("selected_card", "")).upper()
    ):
        return False
    return bool(original and enhanced and original != enhanced)


def remote_variant_evidence(
    payload: dict[str, Any],
) -> tuple[tuple[tuple[str, float], ...], tuple[tuple[str, float], ...]]:
    """保留原图和增强图的合法卡密及其置信度，供云端复核裁决。"""

    return (
        _variant_card_scores(payload.get("ocr_original")),
        _variant_card_scores(payload.get("ocr_enhanced")),
    )


def cloud_resolves_remote_variant_conflict(
    remote: Any,
    cloud: Any,
    *,
    valid_card: Any,
) -> bool:
    """仅在独立云端证据严格支持更高置信度增强结果时解决单槽冲突。"""

    if not getattr(remote, "remote_variant_conflict", False):
        return False
    original = tuple(getattr(remote, "remote_original_card_scores", ()) or ())
    enhanced = tuple(getattr(remote, "remote_enhanced_card_scores", ()) or ())
    cloud_cards = tuple(getattr(cloud, "cards", ()) or ())
    if len(original) != 1 or len(enhanced) != 1 or len(cloud_cards) != 1:
        return False
    if getattr(remote, "psn_cards", ()) or getattr(cloud, "psn_cards", ()):
        return False
    if getattr(cloud, "uncertain_count", 0):
        return False

    original_card, original_score = original[0]
    enhanced_card, enhanced_score = enhanced[0]
    cloud_card = str(cloud_cards[0]).upper()
    if not all(valid_card(card) for card in (original_card, enhanced_card, cloud_card)):
        return False
    if cloud_card != enhanced_card or enhanced_score <= original_score:
        return False
    if len(original_card) != len(enhanced_card):
        return False
    return sum(left != right for left, right in zip(original_card, enhanced_card)) == 1


def _variant_cards(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    cards: list[str] = []
    for item in value.get("cards", []) or []:
        text = str(item.get("text", "") if isinstance(item, dict) else item).upper()
        match = PUBG_CARD_RE.search(text)
        if match and match.group(0) not in cards:
            cards.append(match.group(0))
    return tuple(cards)


def _variant_card_scores(value: Any) -> tuple[tuple[str, float], ...]:
    if not isinstance(value, dict):
        return ()
    scores: dict[str, float] = {}
    for item in value.get("cards", []) or []:
        if isinstance(item, dict):
            text = str(item.get("text", "")).upper()
            try:
                score = float(item.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
        else:
            text = str(item).upper()
            score = 0.0
        match = PUBG_CARD_RE.search(text)
        if match:
            card = match.group(0)
            scores[card] = max(scores.get(card, 0.0), score)
    return tuple(scores.items())
