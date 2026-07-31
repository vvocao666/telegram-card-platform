from __future__ import annotations

from typing import Any
import re


PUBG_CARD_RE = re.compile(
    r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}"
)
CPU_STRUCTURAL_REVIEW_REASONS = frozenset(
    {"pubg_marker_without_valid_card", "pubg_marker_count_mismatch"}
)


def cpu_payload_requires_review(payload: dict[str, Any]) -> bool:
    """CPU 只能触发复核，不能直接替换 GPU 卡密。"""
    cpu = payload.get("cpu_ocr")
    if not isinstance(cpu, dict):
        return False
    if not cpu.get("enabled") or cpu.get("shadow_only"):
        return False
    if not cpu.get("can_affect_result") or cpu.get("confirmation_mode") != "strict":
        return False
    return bool(cpu.get("review_required")) and not bool(cpu.get("roi_conflicts_resolved"))


def cpu_payload_is_available(payload: dict[str, Any]) -> bool:
    cpu = payload.get("cpu_ocr")
    return isinstance(cpu, dict) and bool(cpu.get("available"))


def cpu_structural_review_resolved_by_rebuild(
    reasons: tuple[str, ...],
    *,
    rebuilt_count: int,
    marker_count: int,
    unresolved: bool,
    uncertain_count: int,
) -> bool:
    """Clear only Worker line-parser warnings proven complete by ordered rebuild."""

    return bool(reasons) and set(reasons).issubset(CPU_STRUCTURAL_REVIEW_REASONS) and (
        marker_count > 0
        and rebuilt_count == marker_count
        and not unresolved
        and uncertain_count == 0
    )


def cpu_pubg_candidates(payload: dict[str, Any]) -> tuple[str, ...]:
    """Return exact CPU ROI evidence only when strict production review is active."""
    cpu = payload.get("cpu_ocr")
    if not isinstance(cpu, dict):
        return tuple()
    if (
        not cpu.get("enabled")
        or cpu.get("shadow_only")
        or not cpu.get("can_affect_result")
        or cpu.get("confirmation_mode") != "strict"
        or not cpu.get("review_required")
    ):
        return tuple()
    result: list[str] = []
    for line in cpu.get("lines", []) or []:
        if not isinstance(line, dict):
            continue
        raw_text = str(line.get("raw_text", "")).upper().replace(" ", "")
        for card in PUBG_CARD_RE.findall(raw_text):
            if card not in result:
                result.append(card)
    return tuple(result)


def cpu_pubg_candidate_scores(payload: dict[str, Any]) -> tuple[tuple[str, float], ...]:
    """Return strict CPU candidates together with their line confidence."""
    candidates = set(cpu_pubg_candidates(payload))
    if not candidates:
        return tuple()
    cpu = payload.get("cpu_ocr")
    if not isinstance(cpu, dict):
        return tuple()
    result: list[tuple[str, float]] = []
    for line in cpu.get("lines", []) or []:
        if not isinstance(line, dict):
            continue
        raw_text = str(line.get("raw_text", "")).upper().replace(" ", "")
        try:
            score = float(line.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        for card in PUBG_CARD_RE.findall(raw_text):
            if card in candidates and card not in {item[0] for item in result}:
                result.append((card, score))
    return tuple(result)


def cpu_cloud_confirmed_cards(
    cpu_candidates: tuple[str, ...],
    cloud_cards: tuple[str, ...],
) -> tuple[str, ...]:
    """CPU evidence never wins alone; exact OCR.space agreement is mandatory."""
    cloud = set(cloud_cards)
    return tuple(card for card in cpu_candidates if card in cloud)


def apply_cpu_cloud_confirmations(
    remote_cards: tuple[str, ...],
    confirmed_cards: tuple[str, ...],
    *,
    likely_same_card: Any,
) -> tuple[tuple[str, ...], int]:
    """Replace only a unique same-slot GPU variant with exact dual-source evidence."""
    if not confirmed_cards:
        return remote_cards, 0
    if not remote_cards:
        return confirmed_cards, len(confirmed_cards)

    result = list(remote_cards)
    used: set[str] = set()
    resolved = 0
    for index, remote_card in enumerate(result):
        matches = [
            card
            for card in confirmed_cards
            if card not in used and likely_same_card(remote_card, card)
        ]
        if len(matches) != 1:
            continue
        confirmed = matches[0]
        used.add(confirmed)
        if remote_card != confirmed:
            result[index] = confirmed
            resolved += 1
    for card in confirmed_cards:
        if card not in used and card not in result:
            result.append(card)
            resolved += 1
    return tuple(result), resolved
