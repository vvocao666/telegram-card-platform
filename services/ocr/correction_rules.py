from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectionRule:
    wrong: str
    correct: str
    card_type: str | None = None
    position_index: int | None = None
    confidence: float = 0.5


DEFAULT_RULES: tuple[CorrectionRule, ...] = (
    CorrectionRule("O", "0", card_type="PUBG", confidence=0.9),
    CorrectionRule("I", "1", card_type="PUBG", confidence=0.8),
    CorrectionRule("L", "1", card_type="PUBG", confidence=0.8),
    CorrectionRule("S", "5", card_type="PUBG", confidence=0.7),
    CorrectionRule("B", "8", card_type="PUBG", confidence=0.7),
    CorrectionRule("Z", "2", card_type="PUBG", confidence=0.7),
    CorrectionRule("2", "Z", card_type="PUBG", position_index=19, confidence=0.95),
    CorrectionRule("RN", "M", confidence=0.6),
)


def replacement_map(card_type: str | None = None) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for rule in DEFAULT_RULES:
        if rule.card_type and card_type and rule.card_type != card_type:
            continue
        if len(rule.wrong) != 1 or len(rule.correct) != 1:
            continue
        values.setdefault(rule.wrong, [])
        if rule.correct not in values[rule.wrong]:
            values[rule.wrong].append(rule.correct)
    return {key: tuple(value) for key, value in values.items()}
