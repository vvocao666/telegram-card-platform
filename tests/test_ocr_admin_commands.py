from __future__ import annotations

import json

from services.ocr.admin_commands import (
    export_font_templates,
    format_font_stats,
    format_ocr_review,
    format_ocr_version,
    import_font_templates,
)
from services.ocr.font_repository import FontRepository
from services.ocr.font_templates import FontTemplateRepository


def test_ocr_review_lists_recent_needs_review_records(tmp_path):
    path = tmp_path / "ocr_candidates.json"
    path.write_text(
        json.dumps(
            [
                {"best_candidate": "S07304-AAAA-BBBB-CCCCC", "created_at": "old"},
                {
                    "best_candidate": None,
                    "created_at": "new",
                    "validator_reject_reason": {"BAD": "pubg_prefix_not_s07"},
                },
            ]
        ),
        encoding="utf-8",
    )

    text = format_ocr_review(path)

    assert "OCR Review" in text
    assert "validator_failed" in text
    assert "new" in text
    assert "old" not in text


def test_font_stats_reports_template_name_samples_accuracy_and_last_seen(tmp_path):
    template_repository = FontTemplateRepository(tmp_path / "font_templates.json")
    font_repository = FontRepository(tmp_path / "font_profiles.json")
    font_repository.learn_sample("sample", card_type="PUBG", font_hash="3f9ab2")

    text = format_font_stats(font_repository, template_repository)

    assert "PUBG_FONT_A" in text
    assert "学习次数=218" in text
    assert "准确率=99.3%" in text
    assert "最近学习时间=" in text


def test_export_and_import_font_templates(tmp_path):
    path = tmp_path / "font_templates.json"
    exported = export_font_templates(path)
    payload = exported.read_text(encoding="utf-8")
    data = json.loads(payload)
    data["PUBG_FONT_B"] = dict(data["PUBG_FONT_A"])
    data["PUBG_FONT_B"]["font_hash"] = "font_b"

    count = import_font_templates(json.dumps(data), path)

    assert count == 2
    assert FontTemplateRepository(path).get("PUBG_FONT_B") is not None


def test_ocr_version_reports_counts(tmp_path):
    FontTemplateRepository(tmp_path / "outputs" / "font_templates.json")
    (tmp_path / "outputs" / "today_ocr_cache.json").write_text(
        json.dumps({"date": "2099-01-01", "ocr_cards": ["A", "B"]}),
        encoding="utf-8",
    )

    text = format_ocr_version(tmp_path, current_version="test-version")

    assert "当前版本: test-version" in text
    assert "release: v1.3.0-ocr-learning-plus" in text
    assert "template数量: 1" in text
