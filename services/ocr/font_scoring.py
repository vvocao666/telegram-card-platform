from __future__ import annotations

from dataclasses import dataclass

from services.ocr.candidate_generator import Candidate
from services.ocr.font_profile import FontProfile
from services.ocr.validator import validate_candidate


@dataclass(frozen=True)
class FontScore:
    score: float
    reasons: tuple[str, ...]


def score_with_font_profile(
    candidate: Candidate,
    font_profile: FontProfile | None = None,
    font_hash: str | None = None,
    source_user_id: int | None = None,
) -> FontScore:
    score = 0.0
    reasons: list[str] = []
    if not validate_candidate(candidate.corrected_text, candidate.card_type):
        return FontScore(score=-100.0, reasons=("invalid_format",))
    score += 20.0
    reasons.append("valid_format")
    if len(candidate.changes) == 1:
        score += 10.0
        reasons.append("single_char_change")
    elif len(candidate.changes) > 1:
        score -= 50.0
        reasons.append("global_untrusted_change")
    if font_profile and font_profile.enabled:
        if font_hash and font_profile.font_hash == font_hash:
            score += 40.0
            reasons.append("font_match")
        if source_user_id is not None and font_profile.source_user_id == source_user_id:
            score += 25.0
            reasons.append("source_user_match")
        matched_rule = _matched_font_rule(candidate, font_profile)
        if matched_rule:
            score += 30.0
            reasons.append("learned_rule")
            if matched_rule.startswith("position:"):
                score += 20.0
                reasons.append("position_match")
    elif candidate.changes:
        score -= 50.0
        reasons.append("global_untrusted_change")
    return FontScore(score=score, reasons=tuple(reasons))


def _matched_font_rule(candidate: Candidate, profile: FontProfile) -> str | None:
    for change in candidate.changes:
        parsed = parse_change(change)
        if not parsed:
            continue
        wrong, correct, position = parsed
        pair_key = f"{wrong}>{correct}"
        position_key = f"{position}:{pair_key}"
        if profile.position_rules.get(position_key, 0) > 0:
            return f"position:{position_key}"
        if profile.error_pairs.get(pair_key, 0) > 0:
            return pair_key
    return None


def parse_change(change: str) -> tuple[str, str, int] | None:
    if "->" not in change or "@" not in change:
        return None
    left, position_text = change.rsplit("@", 1)
    wrong, correct = left.split("->", 1)
    try:
        position = int(position_text)
    except ValueError:
        return None
    return wrong, correct, position
