from __future__ import annotations

from dataclasses import dataclass

from services.ocr.font_templates import FontTemplateRepository
from services.ocr.template_matcher import best_template_match
from services.ocr.validator import validate_candidate

AMBIGUOUS_TEMPLATE_PAIRS = {("2", "Z"), ("Z", "2")}


@dataclass(frozen=True)
class CorrectionDecision:
    result: str
    corrected: bool
    needs_review: bool
    reason: str
    score: float


def safe_correct_candidate(
    candidate: str,
    font_hash: str | None = None,
    card_type: str = "PUBG",
    image_quality_score: float = 100.0,
    ocr_confidence: float = 100.0,
    conflict_count: int = 0,
    roi_failed: bool = False,
    repository: FontTemplateRepository | None = None,
) -> CorrectionDecision:
    if image_quality_score < 70 or roi_failed or conflict_count >= 2:
        return CorrectionDecision(candidate, False, True, "needs_review_low_quality_or_conflict", ocr_confidence)

    if validate_candidate(candidate, card_type=card_type) and ocr_confidence >= 90 and conflict_count == 0 and not font_hash:
        return CorrectionDecision(candidate, False, False, "normal_font_protected", ocr_confidence)

    if not font_hash:
        return CorrectionDecision(candidate, False, False, "no_font_template", ocr_confidence)

    match = best_template_match(font_hash, repository=repository)
    if not match or match.similarity < 95 or not match.template.enabled:
        return CorrectionDecision(candidate, False, False, "template_not_matched", ocr_confidence)

    corrected = _apply_counted_template(candidate, match.template, high_weight_only=True)
    if corrected == candidate:
        return CorrectionDecision(candidate, False, False, "no_eligible_rule", ocr_confidence)
    if not validate_candidate(corrected, card_type=card_type):
        return CorrectionDecision(candidate, False, True, "validator_rejected_correction", ocr_confidence)
    return CorrectionDecision(corrected, True, False, "template_correction_applied", match.similarity)


def _apply_counted_template(candidate: str, template, high_weight_only: bool = False) -> str:
    chars = list(candidate)
    for key, correct in template.position_pairs.items():
        if ":" not in key:
            continue
        position_text, wrong = key.split(":", 1)
        try:
            position = int(position_text)
        except ValueError:
            continue
        rule_key = f"{position}:{wrong}>{correct}"
        if (wrong, correct) in AMBIGUOUS_TEMPLATE_PAIRS:
            continue
        min_count = 10 if high_weight_only else 3
        if template.rule_counts.get(rule_key, 0) < min_count:
            continue
        if 0 <= position < len(chars) and chars[position] == wrong:
            chars[position] = correct
    return "".join(chars)
