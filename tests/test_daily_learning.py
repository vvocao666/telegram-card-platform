import json

from services.ocr.daily_learning import (
    extract_ground_truth_cards,
    learn_today,
    learn_today_debug,
    load_today_ocr_results,
    select_learning_ocr_window,
    strict_extraction_missing_cards,
    OcrCardResult,
)
from services.ocr.font_repository import FontRepository
from services.ocr.font_templates import FontTemplateRepository
from services.ocr.today_cache import append_today_ocr_cache


GROUND_TRUTH_TEXT = """
S07304-9M8Q-Y7UW-78Z2U 微信小碗 515
S07304-GM7D-JQ93-9NHLV 淘 538
AK3D-8B8F-DXN2 闲360
"""


def test_extract_ground_truth_cards_ignores_notes_and_prices():
    cards = extract_ground_truth_cards(GROUND_TRUTH_TEXT)

    assert cards == [
        "S07304-9M8Q-Y7UW-78Z2U",
        "S07304-GM7D-JQ93-9NHLV",
        "AK3D-8B8F-DXN2",
    ]


def test_load_today_ocr_results_reads_candidates_cache(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    (output_dir / "ocr_candidates.json").write_text(
        json.dumps(
            [
                {
                    "ocr_result": "S07304-9M8Q-Y7UW-7822U",
                    "font_hash": "pubg_font_a_supplier",
                    "candidate_list": [
                        {"value": "S07304-9M8Q-Y7UW-78Z2U"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    results = load_today_ocr_results(tmp_path)

    assert len(results) == 1
    assert results[0].card == "S07304-9M8Q-Y7UW-7822U"
    assert results[0].font_hash == "pubg_font_a_supplier"


def test_learn_today_diff_and_deduplicates_same_font_rule(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    (output_dir / "ocr_candidates.json").write_text(
        json.dumps(
            [
                {
                    "ocr_result": "S07304-9M8Q-Y7UW-7822U",
                    "font_hash": "pubg_font_a_supplier",
                },
                {
                    "ocr_result": "AK3D-8B8F-DXN2",
                    "font_hash": "psn_font_a_supplier",
                },
            ]
        ),
        encoding="utf-8",
    )
    font_repository = FontRepository(output_dir / "font_profiles.json")
    template_repository = FontTemplateRepository(output_dir / "font_templates.json")
    template_repository.write_templates([])

    first = learn_today(
        GROUND_TRUTH_TEXT,
        base_path=tmp_path,
        font_repository=font_repository,
        template_repository=template_repository,
    )
    second = learn_today(
        GROUND_TRUTH_TEXT,
        base_path=tmp_path,
        font_repository=font_repository,
        template_repository=template_repository,
    )
    profile = font_repository.get_profile("pubg_font_a_supplier")

    assert first.extracted_card_count == 3
    assert first.ocr_correct_count == 1
    assert first.character_correction_count == 1
    assert first.missing_count == 1
    assert first.new_learning_count == 2
    assert second.new_learning_count == 0
    assert profile is not None
    assert profile.position_rules["19:2>Z"] == 1


def test_same_error_different_font_learns_independently(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    font_repository = FontRepository(output_dir / "font_profiles.json")
    template_repository = FontTemplateRepository(output_dir / "font_templates.json")
    template_repository.write_templates([])
    for font_hash in ("font_a", "font_b"):
        (output_dir / "ocr_candidates.json").write_text(
            json.dumps([{"ocr_result": "S07304-9M8Q-Y7UW-7822U", "font_hash": font_hash}]),
            encoding="utf-8",
        )
        learn_today(
            "S07304-9M8Q-Y7UW-78Z2U",
            base_path=tmp_path,
            font_repository=font_repository,
            template_repository=template_repository,
        )

    assert font_repository.get_profile("font_a").position_rules["19:2>Z"] == 1
    assert font_repository.get_profile("font_b").position_rules["19:2>Z"] == 1


def test_loose_human_separators_recover_two_cards():
    text = """
    S07304-7G8D KWXQ-6FZ2F熊533
    S07304-ZTXV-DQTN+ZJ63H熊533
    """

    cards = extract_ground_truth_cards(text)
    strict_missing = strict_extraction_missing_cards(text)

    assert cards == [
        "S07304-7G8D-KWXQ-6FZ2F",
        "S07304-ZTXV-DQTN-ZJ63H",
    ]
    assert strict_missing == cards


def test_learn_today_without_ocr_cache_does_not_mark_all_missing(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    template_repository = FontTemplateRepository(output_dir / "font_templates.json")
    template_repository.write_templates([])

    report = learn_today(
        "S07304-7G8D KWXQ-6FZ2F熊533",
        base_path=tmp_path,
        font_repository=FontRepository(output_dir / "font_profiles.json"),
        template_repository=template_repository,
    )

    assert report.extracted_card_count == 1
    assert not report.ocr_cache_found
    assert report.missing_count == 0
    assert report.new_learning_count == 0


def test_learn_today_debug_reports_set_counts(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    (output_dir / "today_ocr_cache.json").write_text(
        json.dumps(["S07304-AAAA-BBBB-CCCCC", "S07304-WWWW-XXXX-YYYYY"]),
        encoding="utf-8",
    )

    report = learn_today_debug(
        "S07304-AAAA-BBBB-CCCCC\nS07304-DDDD-EEEE-FFFFF",
        base_path=tmp_path,
    )

    assert report.ocr_count == 2
    assert report.human_count == 2
    assert report.intersection_count == 1
    assert report.missing_count == 1
    assert report.error_count == 1
    assert report.human_missing_list == ("S07304-DDDD-EEEE-FFFFF",)
    assert report.ocr_missing_list == ("S07304-WWWW-XXXX-YYYYY",)


def test_learn_today_prefers_today_ocr_cache(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    append_today_ocr_cache(
        ["S07304-AAAA-BBBB-CCCCC", "S07304-WWWW-XXXX-YYYYY"],
        path=output_dir / "today_ocr_cache.json",
    )
    (output_dir / "ocr_candidates.json").write_text(
        json.dumps([{"ocr_result": "S07304-OLD1-BBBB-CCCCC"}]),
        encoding="utf-8",
    )

    report = learn_today_debug(
        "S07304-AAAA-BBBB-CCCCC\nS07304-DDDD-EEEE-FFFFF",
        base_path=tmp_path,
    )

    assert report.ocr_count == 2
    assert report.intersection_count == 1
    assert report.missing_count == 1
    assert report.error_count == 1


def test_learning_uses_cache_window_starting_from_first_human_card(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    append_today_ocr_cache(
        [
            "S07304-BEFO-RE00-00000",
            "S07304-AAAA-BBBB-CCCCC",
            "S07304-DDDD-EEEE-FFFFF",
            "S07304-AFTE-R000-00000",
        ],
        path=output_dir / "today_ocr_cache.json",
    )

    report = learn_today_debug(
        "S07304-AAAA-BBBB-CCCCC\nS07304-DDDD-EEEE-FFFFF",
        base_path=tmp_path,
    )

    assert report.ocr_cache_total_count == 4
    assert report.ocr_count == 2
    assert report.window_start_index == 1
    assert report.intersection_count == 2
    assert report.error_count == 0


def test_learning_window_ignores_duplicate_ocr_cache_entries():
    ocr_cards = [
        OcrCardResult("S07304-AAAA-BBBB-CCCCC"),
        OcrCardResult("S07304-DDDD-EEEE-FFFFF"),
        OcrCardResult("S07304-DDDD-EEEE-FFFFF"),
        OcrCardResult("S07304-1111-2222-33333"),
    ]

    window, start = select_learning_ocr_window(
        ocr_cards,
        ["S07304-DDDD-EEEE-FFFFF", "S07304-1111-2222-33333"],
    )

    assert start == 1
    assert [item.card for item in window] == [
        "S07304-DDDD-EEEE-FFFFF",
        "S07304-1111-2222-33333",
    ]


def test_extract_one_hundred_five_human_cards_with_notes_and_dash_variants():
    strict_cards = [
        f"S07304-{index:04X}-AAAA-BBBBB 微信小碗 515"
        for index in range(103)
    ]
    text = "\n".join(
        [
            *strict_cards,
            "S07304-7G8D KWXQ-6FZ2F熊533",
            "S07304-ZTXV-DQTN+ZJ63H熊533",
        ]
    )

    cards = extract_ground_truth_cards(text)

    assert len(cards) == 105
    assert "S07304-7G8D-KWXQ-6FZ2F" in cards
    assert "S07304-ZTXV-DQTN-ZJ63H" in cards
