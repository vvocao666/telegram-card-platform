from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from services.ocr.pubg_candidate_merge import is_same_slot_conflict


PUBG_CARD_RE = re.compile(
    r"(?<![A-Z0-9])S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}(?![A-Z0-9])"
)
SUSPECT_PUBG_CARD_RE = re.compile(
    r"(?<![A-Z0-9])[A-Z0-9](07[0-9]{3})"
    r"-([A-Z0-9]{4})-([A-Z0-9]{4})-([A-Z0-9]{5})(?![A-Z0-9])"
)
SOURCE_LABELS = {"REMOTE", "OCRSPACE"}


def repeated_pubg_source_consensus(result: Any) -> str | None:
    """返回 Remote 与 OCR.space 重复一致确认的唯一同槽 PUBG 卡。"""

    cards = tuple(str(card).upper() for card in (getattr(result, "cards", ()) or ()))
    if len(cards) != 1 or getattr(result, "psn_cards", ()):
        return None
    confirmed = cards[0]
    sections = _source_sections(str(getattr(result, "raw_text", "") or "").upper())
    remote_cards = _normalized_remote_cards(sections["REMOTE"])
    cloud_cards = PUBG_CARD_RE.findall("\n".join(sections["OCRSPACE"]))
    variant_cards = _variant_cards(result)
    remote_confirmed = remote_cards.count(confirmed) >= 2 or (
        confirmed in variant_cards["original"] and confirmed in variant_cards["enhanced"]
    )
    if not remote_confirmed or cloud_cards.count(confirmed) < 1:
        return None
    if any(card != confirmed for card in remote_cards):
        return None
    if not all(_cloud_candidate_matches_duplicate_slot(card, confirmed) for card in cloud_cards):
        return None
    return confirmed


def _variant_cards(result: Any) -> dict[str, set[str]]:
    def values(attribute: str) -> set[str]:
        return {
            str(card).upper()
            for card, _score in (getattr(result, attribute, ()) or ())
            if card
        }

    return {
        "original": values("remote_original_card_scores"),
        "enhanced": values("remote_enhanced_card_scores"),
    }


def _normalized_remote_cards(lines: list[str]) -> list[str]:
    """Normalize only the damaged first glyph for duplicate-source evidence.

    This helper never returns a production candidate.  It only proves that two
    detected lines have the same `07ddd-4-4-5` body as the already confirmed
    OCR.space card.
    """
    cards: list[str] = []
    for match in SUSPECT_PUBG_CARD_RE.finditer("\n".join(lines)):
        suffix, first, second, tail = match.groups()
        cards.append(f"S{suffix}-{first}-{second}-{tail}")
    return cards


def _cloud_candidate_matches_duplicate_slot(card: str, confirmed: str) -> bool:
    if card == confirmed or is_same_slot_conflict(card, confirmed):
        return True
    card_parts = card.split("-")
    confirmed_parts = confirmed.split("-")
    return len(card_parts) == 4 and card_parts[:2] == confirmed_parts[:2]


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
