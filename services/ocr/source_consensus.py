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
MIN_DUAL_GPU_SCORE = 0.97


def exact_pubg_cross_source_consensus(remote: Any, cloud: Any) -> str | None:
    """Return one exact card independently produced by Remote and OCR.space.

    Both providers must return the same single valid PUBG card, and neither
    raw response may contain another complete valid PUBG candidate.
    """

    remote_card = _single_valid_card(remote)
    cloud_card = _single_valid_card(cloud)
    if remote_card is None or cloud_card is None or remote_card != cloud_card:
        return None
    raw_cards = PUBG_CARD_RE.findall(
        "\n".join(
            (
                str(getattr(remote, "raw_text", "") or "").upper(),
                str(getattr(cloud, "raw_text", "") or "").upper(),
            )
        )
    )
    if any(card != remote_card for card in raw_cards):
        return None
    return remote_card


def repeated_pubg_source_consensus(
    result: Any,
    *,
    cloud_candidates: tuple[str, ...] = (),
    adjacent_wrap_only: bool = False,
) -> str | None:
    """返回 Remote 与 OCR.space 重复一致确认的唯一同槽 PUBG 卡。"""

    cards = tuple(str(card).upper() for card in (getattr(result, "cards", ()) or ()))
    if len(cards) != 1 or getattr(result, "psn_cards", ()):
        return None
    confirmed = cards[0]
    sections = _source_sections(str(getattr(result, "raw_text", "") or "").upper())
    remote_cards = _normalized_remote_cards(sections["REMOTE"])
    cloud_cards = [
        str(card).upper()
        for card in cloud_candidates
        if PUBG_CARD_RE.fullmatch(str(card).upper())
    ] or PUBG_CARD_RE.findall("\n".join(sections["OCRSPACE"]))
    variant_cards = _variant_cards(result)
    adjacent_remote_reconstructions = _count_adjacent_remote_reconstructions(
        sections["REMOTE"], confirmed
    )
    remote_confirmed = adjacent_remote_reconstructions >= 2 or (
        not adjacent_wrap_only
        and (
            remote_cards.count(confirmed) >= 2
            or (
                confirmed in variant_cards["original"]
                and confirmed in variant_cards["enhanced"]
            )
        )
    )
    if not remote_confirmed or not cloud_cards:
        return None
    if any(card != confirmed for card in remote_cards):
        return None
    if not all(_cloud_candidate_matches_duplicate_slot(card, confirmed) for card in cloud_cards):
        return None
    if adjacent_remote_reconstructions >= 2:
        return confirmed
    if cloud_cards.count(confirmed) >= 1:
        return confirmed
    if (
        _high_confidence_dual_gpu_match(result, confirmed)
        and all(_cloud_candidate_is_tail_only_conflict(card, confirmed) for card in cloud_cards)
    ):
        return confirmed
    return None


def _single_valid_card(result: Any) -> str | None:
    cards = tuple(str(card).upper() for card in (getattr(result, "cards", ()) or ()))
    if (
        len(cards) != 1
        or getattr(result, "psn_cards", ())
        or getattr(result, "psn_uncertain", ())
        or not PUBG_CARD_RE.fullmatch(cards[0])
    ):
        return None
    return cards[0]


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


def _high_confidence_dual_gpu_match(result: Any, confirmed: str) -> bool:
    def matching_scores(attribute: str) -> list[float]:
        return [
            float(score)
            for card, score in (getattr(result, attribute, ()) or ())
            if str(card).upper() == confirmed
        ]

    original_scores = matching_scores("remote_original_card_scores")
    enhanced_scores = matching_scores("remote_enhanced_card_scores")
    return (
        bool(original_scores)
        and bool(enhanced_scores)
        and max(original_scores) >= MIN_DUAL_GPU_SCORE
        and max(enhanced_scores) >= MIN_DUAL_GPU_SCORE
    )


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


def _count_adjacent_remote_reconstructions(lines: list[str], confirmed: str) -> int:
    """Count exact wrapped cards reconstructed from two adjacent OCR lines."""
    compact_confirmed = confirmed.replace("-", "")
    count = 0
    for index, line in enumerate(lines):
        normalized = re.sub(r"[^A-Z0-9]", "", line.upper())
        prefix = re.search(r"S07[0-9]{3}", normalized)
        if not prefix:
            continue
        current = normalized[prefix.start() :]
        if current == compact_confirmed:
            continue
        if index + 1 >= len(lines) or not compact_confirmed.startswith(current):
            continue
        next_line = re.sub(r"[^A-Z0-9]", "", lines[index + 1].upper())
        if current + next_line == compact_confirmed:
            count += 1
    return count


def _cloud_candidate_matches_duplicate_slot(card: str, confirmed: str) -> bool:
    if card == confirmed or is_same_slot_conflict(card, confirmed):
        return True
    card_parts = card.split("-")
    confirmed_parts = confirmed.split("-")
    return len(card_parts) == 4 and card_parts[:2] == confirmed_parts[:2]


def _cloud_candidate_is_tail_only_conflict(card: str, confirmed: str) -> bool:
    card_parts = card.split("-")
    confirmed_parts = confirmed.split("-")
    return (
        len(card_parts) == 4
        and len(confirmed_parts) == 4
        and card_parts[:3] == confirmed_parts[:3]
        and card != confirmed
    )


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
