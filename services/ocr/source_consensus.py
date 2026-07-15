from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from services.ocr.pubg_candidate_merge import is_same_slot_conflict


PUBG_CARD_RE = re.compile(
    r"(?<![A-Z0-9])S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}(?![A-Z0-9])"
)
SOURCE_LABELS = {"REMOTE", "OCRSPACE"}


def repeated_pubg_source_consensus(result: Any) -> str | None:
    """返回 Remote 与 OCR.space 重复一致确认的唯一同槽 PUBG 卡。"""

    cards = tuple(str(card).upper() for card in (getattr(result, "cards", ()) or ()))
    if len(cards) != 1 or getattr(result, "psn_cards", ()):
        return None
    confirmed = cards[0]
    sections = _source_sections(str(getattr(result, "raw_text", "") or "").upper())
    remote_cards = PUBG_CARD_RE.findall("\n".join(sections["REMOTE"]))
    cloud_cards = PUBG_CARD_RE.findall("\n".join(sections["OCRSPACE"]))
    if remote_cards.count(confirmed) < 2 or cloud_cards.count(confirmed) < 2:
        return None
    all_cards = remote_cards + cloud_cards
    if not all_cards or not all(
        card == confirmed or is_same_slot_conflict(card, confirmed) for card in all_cards
    ):
        return None
    return confirmed


def _source_sections(raw_text: str) -> dict[str, list[str]]:
    sections: defaultdict[str, list[str]] = defaultdict(list)
    current = ""
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            continue
        if current in SOURCE_LABELS:
            sections[current].append(line)
    return sections
