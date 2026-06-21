from __future__ import annotations

from dataclasses import dataclass

from services.ocr.validator import detect_card_type, normalize_candidate, validate_candidate


@dataclass(frozen=True)
class DuplicateWarning:
    card: str
    existing_card: str
    source: str
    similarity: float


def canonical_card(raw_ocr: str) -> str | None:
    normalized = normalize_candidate(raw_ocr)
    if validate_candidate(normalized):
        return normalized
    return None


def similar_duplicate_warnings(
    cards: list[str],
    source: str,
    existing_cards: list[tuple[str, str]],
    threshold: float = 95.0,
) -> list[DuplicateWarning]:
    warnings: list[DuplicateWarning] = []
    for raw_card in cards:
        card = canonical_card(raw_card)
        if not card:
            continue
        for existing_card, existing_source in existing_cards:
            if existing_source != source:
                continue
            existing = canonical_card(existing_card)
            if not existing or detect_card_type(existing) != detect_card_type(card):
                continue
            similarity = card_similarity(card, existing)
            if card != existing and similarity >= threshold and hamming_distance(card.replace("-", ""), existing.replace("-", "")) <= 1:
                warnings.append(DuplicateWarning(card=card, existing_card=existing, source=source, similarity=similarity))
    return warnings


def card_similarity(left: str, right: str) -> float:
    if len(left) != len(right):
        return 0.0
    distance = hamming_distance(left, right)
    return round((len(left) - distance) / len(left) * 100, 2)


def hamming_distance(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right))
