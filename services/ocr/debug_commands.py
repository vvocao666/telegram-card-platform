from __future__ import annotations

from services.ocr.candidate_audit import build_candidate_audit
from services.ocr.daily_learning import learn_today_debug, strict_extraction_missing_cards
from services.ocr.font_fingerprint import FontFingerprint
from services.ocr.font_repository import FontRepository
from services.ocr.font_templates import FontTemplateRepository
from services.ocr.template_learning import learn_template_sample


def ocr_debug(raw_text: str, card_type: str | None = None) -> str:
    audit = build_candidate_audit(raw_text, card_type=card_type)
    lines = [
        "OCR Debug",
        f"Candidates: {len(audit.candidate_list)}",
        f"Best: {audit.best_candidate or '-'}",
        f"Best score: {audit.best_score if audit.best_score is not None else '-'}",
        f"Rejected: {len(audit.validator_reject_reason)}",
    ]
    return "\n".join(lines)


def ocr_candidates(raw_text: str, card_type: str | None = None) -> str:
    audit = build_candidate_audit(raw_text, card_type=card_type)
    if not audit.candidate_list:
        return "OCR Candidates\n-"
    lines = ["OCR Candidates"]
    for item in audit.candidate_list:
        lines.append(f"{item['value']} | score={item['score']}")
    return "\n".join(lines)


def ocr_font_stats(repository: FontRepository | None = None) -> str:
    repository = repository or FontRepository()
    stats = repository.stats()
    lines = [
        "OCR Font Stats",
        f"Profiles: {stats['profile_count']}",
        f"Samples: {stats['sample_count']}",
    ]
    return "\n".join(lines)


def ocr_fonts(repository: FontRepository | None = None) -> str:
    repository = repository or FontRepository()
    profiles = repository.list_profiles()
    if not profiles:
        return "OCR Fonts\n-"
    lines = ["OCR Fonts"]
    for profile in profiles:
        state = "enabled" if profile.enabled else "disabled"
        lines.append(f"{profile.font_hash} | {profile.card_type or '-'} | samples={profile.sample_count} | {state}")
    return "\n".join(lines)


def ocr_font_rules(font_hash: str, repository: FontRepository | None = None) -> str:
    repository = repository or FontRepository()
    rules = repository.rules_for(font_hash)
    if not rules:
        return f"OCR Font Rules\n{font_hash}: not found"
    return "\n".join(
        [
            "OCR Font Rules",
            f"Font: {rules['font_hash']}",
            f"Enabled: {rules['enabled']}",
            f"Error pairs: {rules['error_pairs']}",
            f"Position rules: {rules['position_rules']}",
            f"Confidence: {rules['confidence']}",
        ]
    )


def ocr_font_enable(font_hash: str, repository: FontRepository | None = None) -> str:
    repository = repository or FontRepository()
    if repository.set_enabled(font_hash, True):
        return f"OCR font enabled: {font_hash}"
    return f"OCR font not found: {font_hash}"


def ocr_font_disable(font_hash: str, repository: FontRepository | None = None) -> str:
    repository = repository or FontRepository()
    if repository.set_enabled(font_hash, False):
        return f"OCR font disabled: {font_hash}"
    return f"OCR font not found: {font_hash}"


def ocr_template_stats(repository: FontTemplateRepository | None = None) -> str:
    repository = repository or FontTemplateRepository()
    stats = repository.stats()
    return "\n".join(
        [
            "OCR Template Stats",
            f"Templates: {stats['template_count']}",
            f"Enabled: {stats['enabled_count']}",
            f"Samples: {stats['sample_count']}",
        ]
    )


def ocr_template_list(repository: FontTemplateRepository | None = None) -> str:
    repository = repository or FontTemplateRepository()
    templates = repository.list_templates()
    if not templates:
        return "OCR Templates\n-"
    lines = ["OCR Templates"]
    for template in templates:
        state = "enabled" if template.enabled else "disabled"
        lines.append(f"{template.name} | {template.card_type} | samples={template.samples} | confidence={template.confidence} | {state}")
    return "\n".join(lines)


def ocr_template_enable(name: str, repository: FontTemplateRepository | None = None) -> str:
    repository = repository or FontTemplateRepository()
    if repository.set_enabled(name, True):
        return f"OCR template enabled: {name}"
    return f"OCR template not found: {name}"


def ocr_template_disable(name: str, repository: FontTemplateRepository | None = None) -> str:
    repository = repository or FontTemplateRepository()
    if repository.set_enabled(name, False):
        return f"OCR template disabled: {name}"
    return f"OCR template not found: {name}"


def ocr_template_learn(
    fingerprint: FontFingerprint,
    ocr_result: str,
    correct_result: str,
    font_repository: FontRepository | None = None,
    template_repository: FontTemplateRepository | None = None,
) -> str:
    result = learn_template_sample(
        fingerprint,
        ocr_result,
        correct_result,
        font_repository=font_repository,
        template_repository=template_repository,
    )
    if result.generated:
        return f"OCR template generated: {result.template_name} samples={result.sample_count}"
    return f"OCR template learning: {result.font_hash} samples={result.sample_count}/100"


def ocr_learn_debug(ground_truth_text: str, base_path=".") -> str:
    report = learn_today_debug(ground_truth_text, base_path=base_path)
    strict_missing = strict_extraction_missing_cards(ground_truth_text)
    lines = [
        "OCR Learn Debug",
        f"OCR cache: {'found' if report.ocr_cache_found else 'missing'}",
        f"OCR数量: {report.ocr_count}",
        f"人工数量: {report.human_count}",
        f"交集数量: {report.intersection_count}",
        f"遗漏数量: {report.missing_count}",
        f"错误数量: {report.error_count}",
        "人工缺失列表:",
        *(report.human_missing_list or ("-",)),
        "OCR缺失列表:",
        *(report.ocr_missing_list or ("-",)),
        "严格格式未提取但已按人工分隔符恢复:",
        *(strict_missing or ("-",)),
    ]
    return "\n".join(lines)
