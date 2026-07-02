from __future__ import annotations

import re
from dataclasses import dataclass


PUBG_CARD_RE = re.compile(r"^S07[A-Z0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}$")


@dataclass(frozen=True)
class DroppedCandidate:
    card: str
    reason: str


@dataclass(frozen=True)
class CandidateMergeResult:
    cards: tuple[str, ...]
    dropped: tuple[DroppedCandidate, ...]


def valid_pubg_card(card: str) -> bool:
    return bool(PUBG_CARD_RE.fullmatch(card))


def exact_unique_cards(cards: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for card in cards:
        if card in seen or not valid_pubg_card(card):
            continue
        seen.add(card)
        result.append(card)
    return result


def card_prefix_key(card: str) -> tuple[str, str, str] | None:
    if not valid_pubg_card(card):
        return None
    first, second, third, _tail = card.split("-")
    return first, second, third


def card_slot_parts(card: str) -> tuple[str, str, str, str] | None:
    if not valid_pubg_card(card):
        return None
    first, second, third, tail = card.split("-")
    return first, second, third, tail


def compact_card(card: str) -> str:
    return card.replace("-", "")


def normalize_line(text: str) -> str:
    return text.upper().replace("—", "-").replace("–", "-").replace("_", "-")


def incomplete_pubg_prefix_keys(lines: list[str] | tuple[str, ...]) -> set[tuple[str, str, str]]:
    blocked: set[tuple[str, str, str]] = set()
    pattern = re.compile(
        r"(S07[A-Z0-9]{3})[^A-Z0-9]+([A-Z0-9]{4})[^A-Z0-9]+([A-Z0-9]{4})(?:[^A-Z0-9]+([A-Z0-9]{0,4}))?"
    )
    for line in lines:
        normalized = normalize_line(line)
        for match in pattern.finditer(normalized):
            tail = match.group(4) or ""
            candidate = f"{match.group(1)}-{match.group(2)}-{match.group(3)}-{tail}"
            if valid_pubg_card(candidate):
                continue
            blocked.add((match.group(1), match.group(2), match.group(3)))
    return blocked


def hamming_distance(left: str, right: str) -> int:
    if len(left) != len(right):
        return max(len(left), len(right))
    return sum(1 for a, b in zip(left, right) if a != b)


def is_same_slot_conflict(left: str, right: str) -> bool:
    left_parts = card_slot_parts(left)
    right_parts = card_slot_parts(right)
    if left_parts is None or right_parts is None:
        return False
    if left_parts[:3] == right_parts[:3]:
        return True
    if left_parts[:2] == right_parts[:2] and hamming_distance(left_parts[2], right_parts[2]) <= 1:
        return True
    return hamming_distance(compact_card(left), compact_card(right)) <= 3


def merge_text_and_worker_pubg_cards(
    text_cards: list[str],
    worker_cards: list[str],
    blocked_prefix_keys: set[tuple[str, str, str]] | None = None,
) -> CandidateMergeResult:
    """保留原始行重建结果，同时补充不冲突的 worker 完整卡。"""
    result = exact_unique_cards(text_cards)
    dropped: list[DroppedCandidate] = []
    seen = set(result)
    blocked = blocked_prefix_keys or set()

    for card in exact_unique_cards(worker_cards):
        if card in seen:
            continue
        key = card_prefix_key(card)
        if key in blocked and not any(card_prefix_key(existing) == key for existing in result):
            dropped.append(DroppedCandidate(card=card, reason="conflict_with_incomplete_text_line"))
            continue
        if any(is_same_slot_conflict(card, existing) for existing in result):
            dropped.append(DroppedCandidate(card=card, reason="conflict_with_line_wrap"))
            continue
        seen.add(card)
        result.append(card)

    return CandidateMergeResult(tuple(result), tuple(dropped))
