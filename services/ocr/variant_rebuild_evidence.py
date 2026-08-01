from __future__ import annotations

import re
from typing import Any


PUBG_COMPACT_RE = re.compile(r"^S07[0-9]{3}[A-Z0-9]{4}[A-Z0-9]{4}[A-Z0-9]{5}$")
COMPLETE_VARIANT_MIN_SCORE = 0.97


def variant_rebuilt_card_scores(
    runtime: Any,
    variant_payload: Any,
) -> tuple[tuple[str, float], ...]:
    """Rebuild exact PUBG evidence from one Worker variant's ordered text lines."""
    if not isinstance(variant_payload, dict):
        return tuple()
    raw_items = variant_payload.get("texts", []) or []
    indexed_items = list(enumerate(raw_items))
    indexed_items.sort(
        key=lambda pair: (*runtime.ocr_item_xy(pair[1]), pair[0])
    )
    items = [item for _index, item in indexed_items if runtime.ocr_item_text(item)]

    evidence: list[tuple[str, float]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        text = runtime.normalize_text(runtime.ocr_item_text(item))
        prefix = re.search(r"S07[0-9]{3}", text)
        if not prefix:
            continue
        compact = re.sub(r"[^A-Z0-9]", "", text[prefix.start() :])
        scores = [_item_score(item)]
        card = _format_complete_card(compact)
        if card:
            _append_evidence(evidence, seen, card, min(scores))
            continue

        for next_index in range(index + 1, min(index + 4, len(items))):
            next_text = runtime.normalize_text(runtime.ocr_item_text(items[next_index]))
            if re.search(r"S07[0-9]{3}", next_text):
                break
            fragment = re.sub(r"[^A-Z0-9]", "", next_text)
            if not fragment:
                break
            compact += fragment
            scores.append(_item_score(items[next_index]))
            if len(compact) > 19:
                break
            card = _format_complete_card(compact)
            if card:
                _append_evidence(evidence, seen, card, min(scores))
                break
    return tuple(evidence)


def complete_original_variant_recovery(
    runtime: Any,
    original_payload: Any,
    enhanced_payload: Any,
    *,
    marker_count: int,
    selected_card_count: int,
) -> tuple[str, ...]:
    """Recover a complete ordered multi-card read when enhancement drops a slot.

    This is deliberately narrower than source voting: the untouched image must
    rebuild every visible slot at high confidence, while the selected/enhanced
    variant is demonstrably incomplete. Character disagreements remain review
    cases and are never corrected here.
    """
    if marker_count < 2 or selected_card_count >= marker_count:
        return tuple()

    original = variant_rebuilt_card_scores(runtime, original_payload)
    enhanced = variant_rebuilt_card_scores(runtime, enhanced_payload)
    if len(original) != marker_count or len(enhanced) >= marker_count:
        return tuple()
    if any(score < COMPLETE_VARIANT_MIN_SCORE for _card, score in original):
        return tuple()

    cards = tuple(card for card, _score in original)
    if len(set(cards)) != marker_count:
        return tuple()
    return cards


def _item_score(item: Any) -> float:
    if not isinstance(item, dict):
        return 0.0
    for key in ("score", "confidence", "rec_score"):
        try:
            return float(item.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    return 0.0


def _format_complete_card(compact: str) -> str:
    if not PUBG_COMPACT_RE.fullmatch(compact):
        return ""
    return f"{compact[:6]}-{compact[6:10]}-{compact[10:14]}-{compact[14:]}"


def _append_evidence(
    evidence: list[tuple[str, float]],
    seen: set[str],
    card: str,
    score: float,
) -> None:
    if card in seen:
        return
    seen.add(card)
    evidence.append((card, score))
