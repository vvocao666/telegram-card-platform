from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from services.ocr.font_fingerprint import FontFingerprint
from services.ocr.font_learning import diff_font_corrections
from services.ocr.font_repository import FontRepository
from services.ocr.font_templates import FontTemplateRepository
from services.ocr.template_learning import learn_template_sample
from services.ocr.today_cache import read_today_ocr_cache
from services.ocr.validator import validate_candidate


PUBG_RE = re.compile(r"S07[A-Z0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}")
DASH_CHARS = r"\-\+_\s‐‑‒–—―－"
PUBG_LOOSE_RE = re.compile(rf"S07[A-Z0-9]{{3}}[{DASH_CHARS}]+[A-Z0-9]{{4}}[{DASH_CHARS}]+[A-Z0-9]{{4}}[{DASH_CHARS}]+[A-Z0-9]{{5}}")
PSN_RE = re.compile(r"(?<![A-Z0-9-])[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}(?![A-Z0-9-])")
DEFAULT_FONT_HASH = "unknown_font"


@dataclass(frozen=True)
class OcrCardResult:
    card: str
    font_hash: str = DEFAULT_FONT_HASH
    font_template: str | None = None
    source: str = ""


@dataclass(frozen=True)
class DailyLearningReport:
    extracted_card_count: int
    ocr_correct_count: int
    character_correction_count: int
    missing_count: int
    new_learning_count: int
    template_sample_total: int
    template_accuracy: float
    ocr_cache_found: bool = False
    ocr_window_found: bool = False


@dataclass(frozen=True)
class LearnDebugReport:
    ocr_count: int
    ocr_cache_total_count: int
    human_count: int
    intersection_count: int
    missing_count: int
    error_count: int
    human_missing_list: tuple[str, ...]
    ocr_missing_list: tuple[str, ...]
    ocr_cache_found: bool
    ocr_window_found: bool
    window_start_index: int


def extract_ground_truth_cards(text: str) -> list[str]:
    normalized = text.upper()
    cards: list[str] = []
    seen: set[str] = set()
    for match in PUBG_LOOSE_RE.finditer(normalized):
        card = re.sub(rf"[{DASH_CHARS}]+", "-", match.group(0))
        if validate_candidate(card, "PUBG") and card not in seen:
            seen.add(card)
            cards.append(card)
    for match in PUBG_RE.finditer(normalized):
        card = match.group(0)
        if validate_candidate(card, "PUBG") and card not in seen:
            seen.add(card)
            cards.append(card)
    for match in PSN_RE.finditer(normalized):
        card = match.group(0)
        if card.startswith("S07"):
            continue
        if validate_candidate(card, "PSN") and card not in seen:
            seen.add(card)
            cards.append(card)
    return cards


def learn_today(
    ground_truth_text: str,
    base_path: Path | str = Path("."),
    font_repository: FontRepository | None = None,
    template_repository: FontTemplateRepository | None = None,
) -> DailyLearningReport:
    base = Path(base_path)
    font_repository = font_repository or FontRepository(base / "outputs" / "font_profiles.json")
    template_repository = template_repository or FontTemplateRepository(base / "outputs" / "font_templates.json")
    truth_cards = extract_ground_truth_cards(ground_truth_text)
    all_ocr_cards = load_today_ocr_results(base)
    ocr_cache_found = bool(all_ocr_cards)
    ocr_cards, window_start_index = select_learning_ocr_window(all_ocr_cards, truth_cards)
    if not ocr_cache_found or not ocr_cards:
        stats = template_repository.stats()
        return DailyLearningReport(
            extracted_card_count=len(truth_cards),
            ocr_correct_count=0,
            character_correction_count=0,
            missing_count=0,
            new_learning_count=0,
            template_sample_total=int(stats["sample_count"]),
            template_accuracy=template_accuracy(template_repository),
            ocr_cache_found=ocr_cache_found,
            ocr_window_found=window_start_index >= 0,
        )
    diff = diff_ocr_with_truth(ocr_cards, truth_cards)
    new_learning_count = 0
    for ocr_card, truth_card in diff["character_confusions"]:
        if learn_character_diff_once(ocr_card, truth_card, font_repository, template_repository):
            new_learning_count += 1
    for truth_card in diff["missing"]:
        if learn_missing_once(truth_card, font_repository):
            new_learning_count += 1
    stats = template_repository.stats()
    return DailyLearningReport(
        extracted_card_count=len(truth_cards),
        ocr_correct_count=len(diff["correct"]),
        character_correction_count=len(diff["character_confusions"]),
        missing_count=len(diff["missing"]),
        new_learning_count=new_learning_count,
        template_sample_total=int(stats["sample_count"]),
        template_accuracy=template_accuracy(template_repository),
        ocr_cache_found=True,
        ocr_window_found=True,
    )


def learn_today_debug(
    ground_truth_text: str,
    base_path: Path | str = Path("."),
) -> LearnDebugReport:
    human_cards = extract_ground_truth_cards(ground_truth_text)
    all_ocr_cards = load_today_ocr_results(base_path)
    ocr_cards, window_start_index = select_learning_ocr_window(all_ocr_cards, human_cards)
    ocr_values = [item.card for item in ocr_cards]
    human_set = set(human_cards)
    ocr_set = set(ocr_values)
    return LearnDebugReport(
        ocr_count=len(ocr_values),
        ocr_cache_total_count=len(all_ocr_cards),
        human_count=len(human_cards),
        intersection_count=len(human_set & ocr_set),
        missing_count=len(human_set - ocr_set) if ocr_values else 0,
        error_count=len(ocr_set - human_set) if ocr_values else 0,
        human_missing_list=tuple(card for card in human_cards if card not in ocr_set) if ocr_values else tuple(),
        ocr_missing_list=tuple(card for card in ocr_values if card not in human_set) if ocr_values else tuple(),
        ocr_cache_found=bool(all_ocr_cards),
        ocr_window_found=bool(ocr_values),
        window_start_index=window_start_index,
    )


def strict_extraction_missing_cards(text: str) -> list[str]:
    strict = set(_extract_strict_ground_truth_cards(text))
    loose = extract_ground_truth_cards(text)
    return [card for card in loose if card not in strict]


def _extract_strict_ground_truth_cards(text: str) -> list[str]:
    normalized = text.upper()
    cards: list[str] = []
    seen: set[str] = set()
    for match in PUBG_RE.finditer(normalized):
        card = match.group(0)
        if validate_candidate(card, "PUBG") and card not in seen:
            seen.add(card)
            cards.append(card)
    for match in PSN_RE.finditer(normalized):
        card = match.group(0)
        if card.startswith("S07"):
            continue
        if validate_candidate(card, "PSN") and card not in seen:
            seen.add(card)
            cards.append(card)
    return cards


def load_today_ocr_results(base_path: Path | str = Path(".")) -> list[OcrCardResult]:
    base = Path(base_path)
    loaders = (
        lambda: _load_today_cache(base / "outputs" / "today_ocr_cache.json"),
        lambda: _load_ocr_report(base / "outputs" / "ocr_report.json"),
        lambda: _load_ocr_candidates(base / "outputs" / "ocr_candidates.json"),
        lambda: _load_generic_cache(base / "outputs" / "today_ocr_cache.json", "today_ocr_cache"),
        lambda: _load_generic_cache(base / "today_ocr_cache.json", "today_ocr_cache"),
        lambda: _load_generic_cache(base / "outputs" / "memory.today_results.json", "memory.today_results"),
        lambda: _load_generic_cache(base / "memory.today_results.json", "memory.today_results"),
    )
    for loader in loaders:
        cards = loader()
        if cards:
            return _dedupe_ocr_cards(cards)
    return []


def select_learning_ocr_window(
    ocr_cards: list[OcrCardResult],
    truth_cards: list[str],
) -> tuple[list[OcrCardResult], int]:
    if not ocr_cards or not truth_cards:
        return [], -1
    ocr_cards = _dedupe_ocr_cards(ocr_cards)
    first_truth = truth_cards[0]
    start_index = _find_learning_start_index(ocr_cards, first_truth)
    if start_index < 0:
        return [], -1
    return ocr_cards[start_index:start_index + len(truth_cards)], start_index


def _load_today_cache(path: Path) -> list[OcrCardResult]:
    data = read_today_ocr_cache(path)
    if not data:
        return []
    return _cards_from_any(data.get("ocr_cards", []), source="outputs/today_ocr_cache.json")


def diff_ocr_with_truth(ocr_cards: list[OcrCardResult], truth_cards: list[str]) -> dict[str, list]:
    truth_set = set(truth_cards)
    ocr_by_card = {item.card: item for item in ocr_cards}
    correct = [card for card in truth_cards if card in ocr_by_card]
    unmatched_truth = [card for card in truth_cards if card not in ocr_by_card]
    unmatched_ocr = [item for item in ocr_cards if item.card not in truth_set]
    character_confusions: list[tuple[OcrCardResult, str]] = []
    used_ocr: set[str] = set()
    missing: list[str] = []
    for truth in unmatched_truth:
        match = _closest_confusion(truth, unmatched_ocr, used_ocr)
        if match:
            character_confusions.append((match, truth))
            used_ocr.add(match.card)
        else:
            missing.append(truth)
    false_positive = [item for item in unmatched_ocr if item.card not in used_ocr]
    return {
        "correct": correct,
        "character_confusions": character_confusions,
        "missing": missing,
        "false_positive": false_positive,
    }


def learn_character_diff_once(
    ocr_card: OcrCardResult,
    truth_card: str,
    font_repository: FontRepository,
    template_repository: FontTemplateRepository,
) -> bool:
    card_type = "PUBG" if truth_card.startswith("S07") else "PSN"
    events = diff_font_corrections(ocr_card.card, truth_card, card_type, ocr_card.font_hash)
    if not events:
        font_repository.touch_profile(ocr_card.font_hash)
        return False
    new_events = [
        event
        for event in events
        if not _event_exists(font_repository, event.font_hash, event.wrong, event.correct, event.position)
    ]
    if not new_events:
        font_repository.touch_profile(ocr_card.font_hash)
        return False
    fingerprint = _fingerprint_for_event(ocr_card.font_hash, card_type)
    learn_template_sample(
        fingerprint,
        ocr_card.card,
        truth_card,
        font_repository=font_repository,
        template_repository=template_repository,
    )
    return True


def learn_missing_once(truth_card: str, font_repository: FontRepository) -> bool:
    font_hash = DEFAULT_FONT_HASH
    profile = font_repository.get_profile(font_hash)
    key = f"missing:{truth_card}"
    if profile and profile.error_pairs.get(key, 0) > 0:
        font_repository.touch_profile(font_hash)
        return False
    card_type = "PUBG" if truth_card.startswith("S07") else "PSN"
    font_repository.learn_sample(
        truth_card,
        card_type=card_type,
        error_pairs={key: 1},
        font_hash=font_hash,
    )
    return True


def template_accuracy(repository: FontTemplateRepository) -> float:
    templates = repository.list_templates()
    if not templates:
        return 0.0
    weighted = sum(template.confidence * template.samples for template in templates)
    samples = sum(template.samples for template in templates)
    return round(weighted / samples, 2) if samples else 0.0


def _load_ocr_report(path: Path) -> list[OcrCardResult]:
    data = _read_json(path)
    if not isinstance(data, dict):
        return []
    values = data.get("ocr_results") or data.get("cards") or data.get("recognized_cards") or []
    return _cards_from_any(values, source="outputs/ocr_report.json")


def _load_ocr_candidates(path: Path) -> list[OcrCardResult]:
    data = _read_json(path)
    if not isinstance(data, list):
        return []
    cards: list[OcrCardResult] = []
    for record in data:
        if not isinstance(record, dict):
            continue
        font_hash = str(record.get("font_hash") or DEFAULT_FONT_HASH)
        font_template = record.get("font_template") if isinstance(record.get("font_template"), str) else None
        for value in _candidate_values(record):
            cards.append(OcrCardResult(card=value, font_hash=font_hash, font_template=font_template, source="outputs/ocr_candidates.json"))
    return cards


def _load_generic_cache(path: Path, source: str) -> list[OcrCardResult]:
    data = _read_json(path)
    return _cards_from_any(data, source=source)


def _cards_from_any(value: object, source: str) -> list[OcrCardResult]:
    cards: list[OcrCardResult] = []
    if isinstance(value, str):
        return [OcrCardResult(card=card, source=source) for card in extract_ground_truth_cards(value)]
    if isinstance(value, list):
        for item in value:
            cards.extend(_cards_from_any(item, source))
    elif isinstance(value, dict):
        font_hash = str(value.get("font_hash") or DEFAULT_FONT_HASH)
        font_template = value.get("font_template") if isinstance(value.get("font_template"), str) else None
        for key in ("card", "best_candidate", "ocr_result", "value"):
            item = value.get(key)
            if isinstance(item, str):
                for card in extract_ground_truth_cards(item):
                    cards.append(OcrCardResult(card=card, font_hash=font_hash, font_template=font_template, source=source))
        for key in ("cards", "ocr_cards", "candidate_list", "results"):
            item = value.get(key)
            if item is not None:
                cards.extend(_cards_from_any(item, source))
    return cards


def _candidate_values(record: dict[str, object]) -> list[str]:
    values: list[str] = []
    for key in ("ocr_result", "recognized_card", "card"):
        value = record.get(key)
        if isinstance(value, str):
            values.extend(extract_ground_truth_cards(value))
    if values:
        return values
    best = record.get("best_candidate")
    if isinstance(best, str):
        values.extend(extract_ground_truth_cards(best))
    candidate_list = record.get("candidate_list")
    if isinstance(candidate_list, list):
        for candidate in candidate_list:
            if isinstance(candidate, dict) and isinstance(candidate.get("value"), str):
                values.extend(extract_ground_truth_cards(str(candidate["value"])))
    return values


def _dedupe_ocr_cards(cards: list[OcrCardResult]) -> list[OcrCardResult]:
    seen: set[str] = set()
    result: list[OcrCardResult] = []
    for card in cards:
        if card.card in seen:
            continue
        seen.add(card.card)
        result.append(card)
    return result


def _find_learning_start_index(cards: list[OcrCardResult], first_truth: str) -> int:
    for index, item in enumerate(cards):
        if item.card == first_truth:
            return index
    first_compact = first_truth.replace("-", "")
    best: tuple[int, int] | None = None
    for index, item in enumerate(cards):
        candidate_compact = item.card.replace("-", "")
        if len(candidate_compact) != len(first_compact):
            continue
        distance = sum(left != right for left, right in zip(candidate_compact, first_compact))
        if 0 < distance <= 2 and (best is None or distance < best[0]):
            best = (distance, index)
    return best[1] if best else -1


def _closest_confusion(truth: str, candidates: list[OcrCardResult], used_ocr: set[str]) -> OcrCardResult | None:
    truth_compact = truth.replace("-", "")
    best: tuple[int, OcrCardResult] | None = None
    for candidate in candidates:
        if candidate.card in used_ocr:
            continue
        candidate_compact = candidate.card.replace("-", "")
        if len(candidate_compact) != len(truth_compact):
            continue
        distance = sum(left != right for left, right in zip(candidate_compact, truth_compact))
        if 0 < distance <= 2 and (best is None or distance < best[0]):
            best = (distance, candidate)
    return best[1] if best else None


def _event_exists(repository: FontRepository, font_hash: str, wrong: str, correct: str, position: int) -> bool:
    profile = repository.get_profile(font_hash)
    if not profile:
        return False
    return profile.position_rules.get(f"{position}:{wrong}>{correct}", 0) > 0


def _fingerprint_for_event(font_hash: str, card_type: str) -> FontFingerprint:
    return FontFingerprint(
        font_hash=font_hash,
        card_type=card_type,
        character_height=0,
        character_width=0,
        line_spacing=0,
        stroke_thickness=0,
        grayscale_bucket=0,
        black_text_ratio=0.0,
        crop_ratio=1.0,
    )


def _read_json(path: Path) -> object:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
