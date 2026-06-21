from dataclasses import replace

from services.ocr.debug_commands import (
    ocr_template_disable,
    ocr_template_enable,
    ocr_template_learn,
    ocr_template_list,
    ocr_template_stats,
)
from services.ocr.font_fingerprint import FontFingerprint
from services.ocr.font_repository import FontRepository
from services.ocr.font_templates import FontTemplate, FontTemplateRepository
from services.ocr.template_learning import learn_template_sample
from services.ocr.template_matcher import apply_template_corrections, match_template


def template_repository(tmp_path) -> FontTemplateRepository:
    repository = FontTemplateRepository(tmp_path / "font_templates.json")
    repository.write_templates(
        [
            FontTemplate(
                name="PUBG_FONT_A",
                font_hash="3f9ab2",
                card_type="PUBG",
                samples=218,
                confusion_pairs={"2": "Z", "8": "B", "M": "N", "Q": "O"},
                position_pairs={"19:2": "Z"},
                rule_counts={"19:2>Z": 12, "2>Z": 12, "8>B": 3, "M>N": 3, "Q>O": 3},
                confidence=99.3,
            ),
            FontTemplate(
                name="PUBG_FONT_B",
                font_hash="4a8bc1",
                card_type="PUBG",
                samples=120,
                confusion_pairs={"0": "O"},
                position_pairs={},
                rule_counts={"0>O": 3},
                confidence=98.0,
            ),
            FontTemplate(
                name="PUBG_FONT_C",
                font_hash="9ff012",
                card_type="PUBG",
                samples=80,
                confusion_pairs={"5": "S"},
                position_pairs={},
                rule_counts={"5>S": 3},
                confidence=97.2,
            ),
        ]
    )
    return repository


def test_match_template_returns_pubg_font_a_when_similarity_over_95(tmp_path):
    repository = template_repository(tmp_path)

    assert match_template("3f9ab2", repository=repository) == "PUBG_FONT_A"


def test_match_template_returns_none_when_similarity_not_enough(tmp_path):
    repository = template_repository(tmp_path)

    assert match_template("abcdef", repository=repository) is None


def test_template_position_rule_corrects_2_to_z_without_global_damage(tmp_path):
    repository = template_repository(tmp_path)

    corrected = apply_template_corrections(
        "S07304-9M8Q-Y7UW-7822U",
        "3f9ab2",
        repository=repository,
    )

    assert corrected == "S07304-9M8Q-Y7UW-78Z2U"


def test_template_does_not_change_legal_card_when_position_does_not_match(tmp_path):
    repository = template_repository(tmp_path)

    corrected = apply_template_corrections(
        "S07304-F2V7-SGH8-NL72X",
        "3f9ab2",
        repository=repository,
    )

    assert corrected == "S07304-F2V7-SGH8-NL72X"


def test_template_commands_list_stats_and_toggle(tmp_path):
    repository = template_repository(tmp_path)

    assert "PUBG_FONT_A" in ocr_template_list(repository)
    assert "Templates: 3" in ocr_template_stats(repository)
    assert "disabled" in ocr_template_disable("PUBG_FONT_A", repository)
    assert "enabled" in ocr_template_enable("PUBG_FONT_A", repository)


def test_template_learning_generates_template_after_one_hundred_samples(tmp_path):
    font_repository = FontRepository(tmp_path / "font_profiles.json")
    template_repo = FontTemplateRepository(tmp_path / "font_templates.json")
    template_repo.write_templates([])
    fingerprint = FontFingerprint(
        font_hash="pubg_font_a_supplier",
        card_type="PUBG",
        character_height=14,
        character_width=8,
        line_spacing=4,
        stroke_thickness=2,
        grayscale_bucket=10,
        black_text_ratio=0.2,
        crop_ratio=1.0,
    )
    result = None
    for _ in range(100):
        result = learn_template_sample(
            fingerprint,
            "S07304-9M8Q-Y7UW-7822U",
            "S07304-9M8Q-Y7UW-78Z2U",
            font_repository=font_repository,
            template_repository=template_repo,
        )

    assert result is not None
    assert result.generated
    assert result.template_name == "PUBG_FONT_SUPPLI"
    assert template_repo.get("PUBG_FONT_SUPPLI") is not None


def test_template_learn_command_reports_progress(tmp_path):
    font_repository = FontRepository(tmp_path / "font_profiles.json")
    template_repo = FontTemplateRepository(tmp_path / "font_templates.json")
    template_repo.write_templates([])
    fingerprint = FontFingerprint(
        font_hash="pubg_font_a_supplier",
        card_type="PUBG",
        character_height=14,
        character_width=8,
        line_spacing=4,
        stroke_thickness=2,
        grayscale_bucket=10,
        black_text_ratio=0.2,
        crop_ratio=1.0,
    )

    output = ocr_template_learn(
        fingerprint,
        "S07304-9M8Q-Y7UW-7822U",
        "S07304-9M8Q-Y7UW-78Z2U",
        font_repository=font_repository,
        template_repository=template_repo,
    )

    assert "samples=1/100" in output


def test_one_hundred_same_font_recognition_accuracy_is_at_least_99_8(tmp_path):
    repository = template_repository(tmp_path)
    ground_truth = "S07304-9M8Q-Y7UW-78Z2U"
    old_result = "S07304-9M8Q-Y7UW-7822U"
    results = [
        apply_template_corrections(old_result, "3f9ab2", repository=repository)
        for _ in range(100)
    ]
    accuracy = sum(result == ground_truth for result in results) / len(results)

    assert accuracy >= 0.998


def test_disabled_template_is_not_used(tmp_path):
    repository = template_repository(tmp_path)
    template = repository.get("PUBG_FONT_A")
    assert template is not None
    repository.save(replace(template, enabled=False))

    corrected = apply_template_corrections(
        "S07304-9M8Q-Y7UW-7822U",
        "3f9ab2",
        repository=repository,
    )

    assert corrected == "S07304-9M8Q-Y7UW-7822U"
