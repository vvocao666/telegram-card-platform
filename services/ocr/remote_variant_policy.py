from __future__ import annotations

import re
from typing import Any


PUBG_CARD_RE = re.compile(r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}")


def remote_variants_conflict(payload: dict[str, Any]) -> bool:
    """原图与增强图都识别出卡密但内容不同时，要求备用 OCR 复核。"""
    original = _variant_cards(payload.get("ocr_original"))
    enhanced = _variant_cards(payload.get("ocr_enhanced"))
    return bool(original and enhanced and original != enhanced)


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
