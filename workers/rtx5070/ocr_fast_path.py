from __future__ import annotations

import re
from typing import Any


PUBG_PREFIX_RE = re.compile(r"S07[0-9A-Z]{3}")
PUBG_CARD_RE = re.compile(r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}")


def enhance_reason(
    metrics: dict[str, Any],
    original_result: dict[str, Any],
    *,
    minimum_card_score: float = 0.985,
    maximum_fast_path_height: int = 500,
    minimum_fast_path_width: int = 350,
    minimum_variance: float = 80.0,
) -> str:
    cards = _unique_cards(original_result.get("cards", []))
    pubg_cards = [item for item in cards if str(item.get("text", "")).startswith("S07")]
    texts = _text_values(original_result.get("texts", []))

    if not cards:
        return "original_cards=0"
    if len(pubg_cards) != len(cards):
        return "non_pubg_or_mixed_cards"
    if len(pubg_cards) != 1:
        return "multi_card_image"
    if _has_incomplete_pubg_line(texts):
        return "incomplete_pubg_line"

    card_score = float(pubg_cards[0].get("score", 0.0) or 0.0)
    if card_score < minimum_card_score:
        return "card_score<0.985"
    if _repeated_exact_card_evidence(
        original_result.get("texts", []),
        str(pubg_cards[0]["text"]),
        minimum_card_score,
    ):
        return "not_needed"

    width = int(metrics.get("width", 0) or 0)
    height = int(metrics.get("height", 0) or 0)
    variance = float(metrics.get("image_variance", 0.0) or 0.0)
    if width <= 0 or height <= 0:
        return "image_metrics_unavailable"
    if width < minimum_fast_path_width:
        return "width<350"
    if height > maximum_fast_path_height:
        return "height>500"
    if variance < minimum_variance:
        return "image_variance<80"
    return "not_needed"


def _repeated_exact_card_evidence(
    items: list[Any],
    card: str,
    minimum_score: float,
) -> bool:
    matches = 0
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("text", "")).upper()
            try:
                score = float(item.get("score", 0.0) or 0.0)
            except (TypeError, ValueError):
                score = 0.0
        else:
            text = str(item).upper()
            score = 0.0
        found = PUBG_CARD_RE.findall(text)
        if any(candidate != card for candidate in found):
            return False
        if card in found and score >= minimum_score:
            matches += 1
    return matches >= 2


def _unique_cards(items: list[Any]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            score = float(item.get("score", 0.0) or 0.0)
        else:
            text = str(item).strip()
            score = 0.0
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append({"text": text, "score": score})
    return unique


def _text_values(items: list[Any]) -> list[str]:
    values: list[str] = []
    for item in items:
        if isinstance(item, dict):
            value = str(item.get("text", "")).strip()
        else:
            value = str(item).strip()
        if value:
            values.append(value)
    return values


def _has_incomplete_pubg_line(texts: list[str]) -> bool:
    for text in texts:
        if not PUBG_PREFIX_RE.search(text):
            continue
        if PUBG_CARD_RE.search(text):
            continue
        compact = text.replace(" ", "")
        groups = compact.split("-")
        if len(groups) != 4 or len(groups[1]) != 4 or len(groups[2]) != 4 or len(groups[3]) != 5:
            return True
    return False
