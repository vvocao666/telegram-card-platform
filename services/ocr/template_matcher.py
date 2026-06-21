from __future__ import annotations

from dataclasses import dataclass

from services.ocr.font_templates import FontTemplate, FontTemplateRepository
from services.ocr.validator import validate_candidate


MATCH_THRESHOLD = 95.0


@dataclass(frozen=True)
class TemplateMatch:
    template: FontTemplate
    similarity: float


def font_hash_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 100.0
    left_core = _hash_core(left)
    right_core = _hash_core(right)
    length = max(len(left_core), len(right_core), 1)
    matches = sum(1 for left_char, right_char in zip(left_core, right_core) if left_char == right_char)
    return round(matches / length * 100, 2)


def match_template(
    font_hash: str,
    repository: FontTemplateRepository | None = None,
    threshold: float = MATCH_THRESHOLD,
) -> str | None:
    match = best_template_match(font_hash, repository=repository, threshold=threshold)
    return match.template.name if match else None


def best_template_match(
    font_hash: str,
    repository: FontTemplateRepository | None = None,
    threshold: float = MATCH_THRESHOLD,
) -> TemplateMatch | None:
    repository = repository or FontTemplateRepository()
    matches = [
        TemplateMatch(template=template, similarity=font_hash_similarity(font_hash, template.font_hash))
        for template in repository.list_templates(enabled_only=True)
    ]
    if not matches:
        return None
    best = max(matches, key=lambda item: item.similarity)
    if best.similarity > threshold:
        return best
    return None


def apply_template_corrections(
    candidate: str,
    font_hash: str,
    card_type: str = "PUBG",
    repository: FontTemplateRepository | None = None,
    threshold: float = MATCH_THRESHOLD,
) -> str:
    match = best_template_match(font_hash, repository=repository, threshold=threshold)
    if not match:
        return candidate
    corrected = apply_template(candidate, match.template)
    if validate_candidate(corrected, card_type=card_type):
        return corrected
    return candidate


def apply_template(candidate: str, template: FontTemplate) -> str:
    chars = list(candidate)
    original_valid = validate_candidate(candidate, card_type=template.card_type)
    for key, correct in template.position_pairs.items():
        if ":" not in key:
            continue
        position_text, wrong = key.split(":", 1)
        try:
            position = int(position_text)
        except ValueError:
            continue
        if 0 <= position < len(chars) and chars[position] == wrong:
            chars[position] = correct
    if original_valid:
        return "".join(chars)
    for index, char in enumerate(chars):
        if char in template.confusion_pairs:
            chars[index] = template.confusion_pairs[char]
    return "".join(chars)


def _hash_core(font_hash: str) -> str:
    if "_" not in font_hash:
        return font_hash
    return font_hash.rsplit("_", 1)[-1]
