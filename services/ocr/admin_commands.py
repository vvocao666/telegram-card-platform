from __future__ import annotations

import json
import subprocess
from pathlib import Path

from services.ocr.font_repository import FontRepository
from services.ocr.font_templates import FontTemplateRepository
from services.ocr.today_cache import read_today_ocr_cache


DEFAULT_RELEASE = "v1.3.0-ocr-learning-plus"


def format_ocr_review(path: Path | str = Path("outputs/ocr_candidates.json"), limit: int = 20) -> str:
    records = _review_records(Path(path), limit=limit)
    lines = ["OCR Review"]
    if not records:
        lines.append("-")
        return "\n".join(lines)
    for index, record in enumerate(records, start=1):
        created_at = str(record.get("created_at") or "-")
        best = str(record.get("best_candidate") or "-")
        reasons = _review_reasons(record)
        lines.append(f"{index}. {created_at}")
        lines.append(f"Best: {best}")
        lines.append(f"Reason: {', '.join(reasons)}")
    return "\n".join(lines)


def format_font_stats(
    font_repository: FontRepository | None = None,
    template_repository: FontTemplateRepository | None = None,
) -> str:
    font_repository = font_repository or FontRepository()
    template_repository = template_repository or FontTemplateRepository()
    profiles = font_repository.list_profiles()
    templates = template_repository.list_templates()
    lines = ["OCR Font Stats"]
    if templates:
        for template in templates:
            lines.append(
                f"{template.name} | 学习次数={template.samples} | 准确率={template.confidence}% | 最近学习时间={_template_last_seen(template.font_hash, profiles)}"
            )
    elif profiles:
        for profile in profiles:
            lines.append(
                f"{profile.font_hash} | 学习次数={profile.sample_count} | 准确率={round(profile.confidence * 100, 2)}% | 最近学习时间={profile.last_seen or '-'}"
            )
    else:
        lines.append("-")
    return "\n".join(lines)


def export_font_templates(path: Path | str = Path("outputs/font_templates.json")) -> Path:
    template_path = Path(path)
    FontTemplateRepository(template_path)
    return template_path


def import_font_templates(payload: str, path: Path | str = Path("outputs/font_templates.json")) -> int:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("font template payload must be a JSON object")
    repository = FontTemplateRepository(path)
    imported = []
    for name, value in data.items():
        if not isinstance(value, dict):
            continue
        template = repository.get(str(name))
        merged = dict(value)
        if template and "enabled" not in merged:
            merged["enabled"] = template.enabled
        imported.append((str(name), merged))
    if not imported:
        raise ValueError("no valid font templates found")
    current = repository._read()
    for name, value in imported:
        current[name] = value
    repository._write(current)
    return len(imported)


def format_ocr_version(
    base_path: Path | str = Path("."),
    release: str = DEFAULT_RELEASE,
    current_version: str = "",
    template_repository: FontTemplateRepository | None = None,
    font_repository: FontRepository | None = None,
) -> str:
    base = Path(base_path)
    template_repository = template_repository or FontTemplateRepository(base / "outputs" / "font_templates.json")
    font_repository = font_repository or FontRepository(base / "outputs" / "font_profiles.json")
    templates = template_repository.list_templates()
    cache = read_today_ocr_cache(base / "outputs" / "today_ocr_cache.json")
    rule_count = sum(len(template.rule_counts) + len(template.position_pairs) + len(template.confusion_pairs) for template in templates)
    rule_count += sum(len(profile.error_pairs) + len(profile.position_rules) for profile in font_repository.list_profiles())
    cache_count = len(cache.get("ocr_cards", [])) if isinstance(cache, dict) and isinstance(cache.get("ocr_cards"), list) else 0
    lines = [
        "OCR Version",
        f"当前版本: {current_version or '-'}",
        f"git commit: {_git_commit(base)}",
        f"release: {release}",
        f"template数量: {len(templates)}",
        f"rule数量: {rule_count}",
        f"cache数量: {cache_count}",
    ]
    return "\n".join(lines)


def _review_records(path: Path, limit: int) -> list[dict[str, object]]:
    data = _read_json(path)
    if not isinstance(data, list):
        return []
    records = [record for record in data if isinstance(record, dict) and _needs_review(record)]
    return records[-limit:][::-1]


def _needs_review(record: dict[str, object]) -> bool:
    if record.get("needs_review") is True:
        return True
    if record.get("image_quality_score") is not None:
        try:
            if float(record.get("image_quality_score")) < 70:
                return True
        except (TypeError, ValueError):
            pass
    reject = record.get("validator_reject_reason")
    if isinstance(reject, dict) and reject:
        return True
    candidates = record.get("candidate_list")
    if isinstance(candidates, list) and len(candidates) > 1:
        valid_values = [item for item in candidates if isinstance(item, dict) and item.get("score") is not None]
        if len(valid_values) > 1 and not record.get("best_candidate"):
            return True
    return False


def _review_reasons(record: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    if record.get("needs_review") is True:
        reasons.append("needs_review")
    if record.get("image_quality_score") is not None:
        try:
            if float(record.get("image_quality_score")) < 70:
                reasons.append("low_quality_image")
        except (TypeError, ValueError):
            pass
    reject = record.get("validator_reject_reason")
    if isinstance(reject, dict) and reject:
        reasons.append("validator_failed")
    candidates = record.get("candidate_list")
    if isinstance(candidates, list) and len(candidates) > 1 and not record.get("best_candidate"):
        reasons.append("ocr_conflict")
    return reasons or ["unknown"]


def _template_last_seen(font_hash: str, profiles) -> str:
    values = [profile.last_seen for profile in profiles if profile.font_hash == font_hash and profile.last_seen]
    return max(values) if values else "-"


def _git_commit(base_path: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=base_path, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "-"


def _read_json(path: Path) -> object:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
