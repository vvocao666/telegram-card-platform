from __future__ import annotations

from dataclasses import dataclass

from services.ocr.font_fingerprint import FontFingerprint
from services.ocr.font_learning import learn_font_correction
from services.ocr.font_repository import FontRepository
from services.ocr.font_templates import FontTemplate, FontTemplateRepository, TEMPLATE_MIN_SAMPLE_COUNT


@dataclass(frozen=True)
class TemplateLearningResult:
    font_hash: str
    sample_count: int
    template_name: str | None
    generated: bool


def learn_template_sample(
    fingerprint: FontFingerprint,
    ocr_result: str,
    correct_result: str,
    font_repository: FontRepository | None = None,
    template_repository: FontTemplateRepository | None = None,
    source_chat_id: int | None = None,
    source_user_id: int | None = None,
) -> TemplateLearningResult:
    font_repository = font_repository or FontRepository()
    template_repository = template_repository or FontTemplateRepository()
    learn_font_correction(
        ocr_result,
        correct_result,
        fingerprint.card_type or "PUBG",
        fingerprint.font_hash,
        font_repository,
        source_chat_id=source_chat_id,
        source_user_id=source_user_id,
    )
    profile = font_repository.get_profile(fingerprint.font_hash)
    sample_count = profile.sample_count if profile else 0
    if not profile or sample_count < TEMPLATE_MIN_SAMPLE_COUNT:
        return TemplateLearningResult(
            font_hash=fingerprint.font_hash,
            sample_count=sample_count,
            template_name=None,
            generated=False,
        )
    template = template_from_profile(profile.font_hash, profile.card_type or "PUBG", sample_count, profile.error_pairs, profile.position_rules)
    template_repository.save(template)
    return TemplateLearningResult(
        font_hash=fingerprint.font_hash,
        sample_count=sample_count,
        template_name=template.name,
        generated=True,
    )


def template_from_profile(
    font_hash: str,
    card_type: str,
    sample_count: int,
    error_pairs: dict[str, int],
    position_rules: dict[str, int],
) -> FontTemplate:
    return FontTemplate(
        name=template_name_for(card_type, font_hash),
        font_hash=font_hash,
        card_type=card_type,
        samples=sample_count,
        confusion_pairs=_best_error_map(error_pairs),
        position_pairs=_best_position_map(position_rules),
        rule_counts={**error_pairs, **position_rules},
        confidence=min(99.9, 95.0 + min(sample_count, 100) / 20),
        enabled=True,
    )


def template_name_for(card_type: str, font_hash: str) -> str:
    suffix = font_hash.rsplit("_", 1)[-1][:6].upper()
    return f"{card_type.upper()}_FONT_{suffix}"


def _best_error_map(error_pairs: dict[str, int]) -> dict[str, str]:
    result: dict[str, tuple[str, int]] = {}
    for pair, count in error_pairs.items():
        if ">" not in pair:
            continue
        wrong, correct = pair.split(">", 1)
        current = result.get(wrong)
        if not current or count > current[1]:
            result[wrong] = (correct, count)
    return {wrong: correct for wrong, (correct, _) in result.items()}


def _best_position_map(position_rules: dict[str, int]) -> dict[str, str]:
    result: dict[str, tuple[str, int]] = {}
    for pair, count in position_rules.items():
        if ":" not in pair or ">" not in pair:
            continue
        position, change = pair.split(":", 1)
        wrong, correct = change.split(">", 1)
        key = f"{position}:{wrong}"
        current = result.get(key)
        if not current or count > current[1]:
            result[key] = (correct, count)
    return {key: correct for key, (correct, _) in result.items()}
