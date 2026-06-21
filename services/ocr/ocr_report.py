from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


DEFAULT_OCR_REPORT_PATH = Path("outputs/ocr_report.json")


@dataclass(frozen=True)
class OcrReport:
    total_images: int
    total_cards: int
    fixed_count: int
    false_negative_count: int
    character_confusion_count: int
    font_profile_hits: int
    font_profile_misses: int
    top_error_pairs: list[tuple[str, int]]
    precision: float
    recall: float
    f1: float


def build_ocr_report(
    total_images: int,
    total_cards: int,
    correct_count: int,
    predicted_count: int,
    fixed_count: int = 0,
    false_negative_count: int = 0,
    character_confusion_count: int = 0,
    font_profile_hits: int = 0,
    font_profile_misses: int = 0,
    error_pairs: dict[str, int] | None = None,
) -> OcrReport:
    precision = correct_count / predicted_count if predicted_count else 0.0
    recall = correct_count / total_cards if total_cards else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return OcrReport(
        total_images=total_images,
        total_cards=total_cards,
        fixed_count=fixed_count,
        false_negative_count=false_negative_count,
        character_confusion_count=character_confusion_count,
        font_profile_hits=font_profile_hits,
        font_profile_misses=font_profile_misses,
        top_error_pairs=sorted((error_pairs or {}).items(), key=lambda item: item[1], reverse=True)[:10],
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
    )


def write_ocr_report(report: OcrReport, output_path: Path | str = DEFAULT_OCR_REPORT_PATH) -> OcrReport:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return report
