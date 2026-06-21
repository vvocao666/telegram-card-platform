from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.ocr.daily_learning import extract_ground_truth_cards, learn_today, learn_today_debug
from services.ocr.font_repository import FontRepository
from services.ocr.font_templates import FontTemplateRepository


@dataclass(frozen=True)
class LearningPreview:
    card_count: int
    ocr_cache_found: bool
    message: str
    preview_cards: tuple[str, ...] = tuple()


def build_learning_preview(text: str, base_path: Path | str = Path(".")) -> LearningPreview:
    cards = extract_ground_truth_cards(text)
    debug = learn_today_debug(text, base_path=base_path)
    if not debug.ocr_cache_found:
        return LearningPreview(
            card_count=len(cards),
            ocr_cache_found=False,
            message="未找到今日OCR缓存，请先发送图片识别，或使用 /ocr_cache_today 查看。",
            preview_cards=tuple(cards[:10]),
        )
    preview_lines = "\n".join(cards[:10]) if cards else "-"
    return LearningPreview(
        card_count=len(cards),
        ocr_cache_found=True,
        message=(
            f"检测到 {len(cards)} 条人工正确卡密。\n"
            "是否用于今日 OCR 学习？\n\n"
            "预览前10条：\n"
            f"{preview_lines}\n\n"
            "回复：\n"
            "/learn_confirm 确认学习\n"
            "/learn_cancel 取消"
        ),
        preview_cards=tuple(cards[:10]),
    )


def execute_learning(text: str, base_path: Path | str = Path(".")) -> str:
    debug = learn_today_debug(text, base_path=base_path)
    if not debug.ocr_cache_found:
        return "未找到今日OCR缓存，请先发送图片识别，或使用 /ocr_cache_today 查看。"
    report = learn_today(text, base_path=base_path)
    font_repository = FontRepository(Path(base_path) / "outputs" / "font_profiles.json")
    template_repository = FontTemplateRepository(Path(base_path) / "outputs" / "font_templates.json")
    return format_learning_report(
        human_count=debug.human_count,
        ocr_count=debug.ocr_count,
        correct_count=debug.intersection_count,
        character_errors=report.character_correction_count,
        missing_count=debug.missing_count,
        false_positive_count=debug.error_count,
        duplicate_count=0,
        font_repository=font_repository,
        template_repository=template_repository,
    )


def format_learning_report(
    human_count: int,
    ocr_count: int,
    correct_count: int,
    character_errors: int,
    missing_count: int,
    false_positive_count: int,
    duplicate_count: int,
    font_repository: FontRepository,
    template_repository: FontTemplateRepository,
) -> str:
    top_pairs = _top_error_pairs(font_repository)
    templates = template_repository.list_templates()
    sample_total = sum(template.samples for template in templates)
    accuracy = round(
        sum(template.samples * template.confidence for template in templates) / sample_total,
        2,
    ) if sample_total else 0.0
    lines = [
        "今日OCR学习完成",
        "",
        f"人工卡密：{human_count}",
        f"OCR缓存：{ocr_count}",
        f"完全正确：{correct_count}",
        f"字符错误：{character_errors}",
        f"漏识别：{missing_count}",
        f"多识别：{false_positive_count}",
        f"重复：{duplicate_count}",
        "",
        "新增学习规则TOP10：",
    ]
    if top_pairs:
        lines.extend(f"{pair.replace('>', ' -> ')}：{count}次" for pair, count in top_pairs[:10])
    else:
        lines.append("-")
    lines.extend(["", "字体模板："])
    if templates:
        lines.append(f"模板数量：{len(templates)}")
        lines.append("命中模板：" + "、".join(template.name for template in templates))
        lines.append(f"样本总数：{sample_total}")
        lines.append(f"当前模板准确率：{accuracy}%")
    else:
        lines.extend(["模板数量：0", "命中模板：-", "样本总数：0", "当前模板准确率：0.0%"])
    lines.extend(["", "缓存文件：", "outputs/today_ocr_cache.json"])
    return "\n".join(lines)


def format_learning_stats(base_path: Path | str = Path(".")) -> str:
    font_repository = FontRepository(Path(base_path) / "outputs" / "font_profiles.json")
    template_repository = FontTemplateRepository(Path(base_path) / "outputs" / "font_templates.json")
    stats = font_repository.stats()
    templates = template_repository.list_templates()
    missing = _top_missing(font_repository)
    char_total = sum(count for _, count in _top_error_pairs(font_repository))
    missing_total = sum(count for _, count in missing)
    recent = _recent_learning_time(font_repository)
    lines = [
        "OCR Learning Stats",
        f"累计人工样本数：{stats['sample_count']}",
        f"累计学习次数：{stats['sample_count']}",
        f"累计学习规则数：{_rule_count(font_repository)}",
        f"累计字符纠错数：{char_total}",
        f"累计漏识别数：{missing_total}",
        "累计重复提醒数：0",
        f"字体模板总数：{len(templates)}",
        "TOP10字符混淆：",
    ]
    top_pairs = _top_error_pairs(font_repository)[:10]
    if top_pairs:
        lines.extend(f"{pair.replace('>', ' -> ')}：{count}次" for pair, count in top_pairs)
    else:
        lines.append("-")
    lines.append("TOP10漏识别：")
    if missing:
        lines.extend(f"{card}：{count}次" for card, count in missing[:10])
    else:
        lines.append("-")
    lines.append("各模板准确率：")
    if templates:
        for template in templates:
            lines.append(f"{template.name}：{template.confidence}%")
    else:
        lines.append("-")
    lines.append(f"最近一次学习时间：{recent or '-'}")
    return "\n".join(lines)


def _top_error_pairs(repository: FontRepository) -> list[tuple[str, int]]:
    pairs: dict[str, int] = {}
    for profile in repository.list_profiles():
        for key, value in profile.error_pairs.items():
            if key.startswith("missing:"):
                continue
            pairs[key] = pairs.get(key, 0) + value
    return sorted(pairs.items(), key=lambda item: item[1], reverse=True)


def _top_missing(repository: FontRepository) -> list[tuple[str, int]]:
    values: dict[str, int] = {}
    for profile in repository.list_profiles():
        for key, count in profile.error_pairs.items():
            if not key.startswith("missing:"):
                continue
            values[key.removeprefix("missing:")] = values.get(key.removeprefix("missing:"), 0) + count
    return sorted(values.items(), key=lambda item: item[1], reverse=True)


def _rule_count(repository: FontRepository) -> int:
    return sum(
        len(profile.error_pairs) + len(profile.position_rules)
        for profile in repository.list_profiles()
    )


def _recent_learning_time(repository: FontRepository) -> str:
    values = [profile.last_seen for profile in repository.list_profiles() if profile.last_seen]
    return max(values) if values else ""
