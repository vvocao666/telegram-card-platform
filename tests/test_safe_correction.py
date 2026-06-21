from services.ocr.font_templates import FontTemplate, FontTemplateRepository
from services.ocr.safe_correction import safe_correct_candidate


def template_repository(tmp_path, rule_count: int = 12) -> FontTemplateRepository:
    repository = FontTemplateRepository(tmp_path / "font_templates.json")
    repository.write_templates(
        [
            FontTemplate(
                name="PUBG_FONT_A",
                font_hash="3f9ab2",
                card_type="PUBG",
                samples=218,
                confusion_pairs={"2": "Z"},
                position_pairs={"19:2": "Z"},
                rule_counts={"19:2>Z": rule_count, "2>Z": rule_count},
                confidence=99.3,
            )
        ]
    )
    return repository


def test_normal_clear_font_is_not_corrected(tmp_path):
    decision = safe_correct_candidate(
        "S07304-F2V7-SGH8-NL72X",
        font_hash=None,
        image_quality_score=95,
        ocr_confidence=96,
        repository=template_repository(tmp_path),
    )

    assert not decision.corrected
    assert not decision.needs_review
    assert decision.result == "S07304-F2V7-SGH8-NL72X"
    assert decision.reason == "normal_font_protected"


def test_special_font_enables_2_to_z_when_rule_count_is_high(tmp_path):
    decision = safe_correct_candidate(
        "S07304-9M8Q-Y7UW-7822U",
        font_hash="3f9ab2",
        image_quality_score=88,
        ocr_confidence=80,
        repository=template_repository(tmp_path, rule_count=12),
    )

    assert decision.corrected
    assert decision.result == "S07304-9M8Q-Y7UW-78Z2U"


def test_special_font_rule_under_ten_does_not_auto_correct(tmp_path):
    decision = safe_correct_candidate(
        "S07304-9M8Q-Y7UW-7822U",
        font_hash="3f9ab2",
        image_quality_score=88,
        ocr_confidence=80,
        repository=template_repository(tmp_path, rule_count=3),
    )

    assert not decision.corrected
    assert decision.result == "S07304-9M8Q-Y7UW-7822U"


def test_blurry_image_does_not_force_correction(tmp_path):
    decision = safe_correct_candidate(
        "S07304-9M8Q-Y7UW-7822U",
        font_hash="3f9ab2",
        image_quality_score=45,
        repository=template_repository(tmp_path),
    )

    assert not decision.corrected
    assert decision.needs_review
