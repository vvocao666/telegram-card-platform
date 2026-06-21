from __future__ import annotations

from dataclasses import dataclass

from services.ocr.font_profile import FontProfile, build_font_profile
from services.ocr.font_repository import FontRepository


@dataclass(frozen=True)
class FontLearningEvent:
    card_type: str
    font_hash: str
    wrong: str
    correct: str
    position: int
    count: int


def learn_font_correction(
    ocr_result: str,
    correct_result: str,
    card_type: str,
    font_hash: str,
    repository: FontRepository,
    source_chat_id: int | None = None,
    source_user_id: int | None = None,
) -> list[FontLearningEvent]:
    events = diff_font_corrections(ocr_result, correct_result, card_type=card_type, font_hash=font_hash)
    if not events:
        return []
    error_pairs = {f"{event.wrong}>{event.correct}": event.count for event in events}
    position_rules = {f"{event.position}:{event.wrong}>{event.correct}": event.count for event in events}
    profile = build_font_profile(
        correct_result,
        card_type=card_type,
        error_pairs=error_pairs,
        position_rules=position_rules,
        source_chat_id=source_chat_id,
        source_user_id=source_user_id,
        confidence=0.9,
        font_hash=font_hash,
    )
    repository.save_profile(profile)
    return events


def diff_font_corrections(
    ocr_result: str,
    correct_result: str,
    card_type: str,
    font_hash: str,
) -> list[FontLearningEvent]:
    if len(ocr_result) != len(correct_result):
        return []
    events: list[FontLearningEvent] = []
    for index, (wrong, correct) in enumerate(zip(ocr_result, correct_result)):
        if wrong == correct:
            continue
        events.append(
            FontLearningEvent(
                card_type=card_type,
                font_hash=font_hash,
                wrong=wrong,
                correct=correct,
                position=index,
                count=1,
            )
        )
    return events


def profile_has_rule(profile: FontProfile, wrong: str, correct: str, position: int | None = None) -> bool:
    pair_key = f"{wrong}>{correct}"
    if position is not None and profile.position_rules.get(f"{position}:{pair_key}", 0) > 0:
        return True
    return profile.error_pairs.get(pair_key, 0) > 0
