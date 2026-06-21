from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class LearnedCorrection:
    card_type: str
    wrong_text: str
    correct_text: str
    wrong_char: str
    correct_char: str
    position_index: int
    count: int
    updated_at: str


def diff_correction(wrong_text: str, correct_text: str, card_type: str) -> list[LearnedCorrection]:
    learned: list[LearnedCorrection] = []
    updated_at = datetime.now(timezone.utc).isoformat()
    for index, (wrong_char, correct_char) in enumerate(zip(wrong_text, correct_text)):
        if wrong_char == correct_char:
            continue
        learned.append(
            LearnedCorrection(
                card_type=card_type,
                wrong_text=wrong_text,
                correct_text=correct_text,
                wrong_char=wrong_char,
                correct_char=correct_char,
                position_index=index,
                count=1,
                updated_at=updated_at,
            )
        )
    return learned


def merge_learning_counts(existing_count: int, increment: int = 1) -> int:
    return max(0, existing_count) + max(1, increment)
