from services.ocr.debug_commands import (
    ocr_candidates,
    ocr_debug,
    ocr_font_disable,
    ocr_font_enable,
    ocr_font_rules,
    ocr_font_stats,
    ocr_fonts,
    ocr_learn_debug,
)
from services.ocr.font_repository import FontRepository


def test_ocr_debug_reports_best_candidate():
    output = ocr_debug("S07304-GM7D-\nJQ93-9NHLV", card_type="PUBG")

    assert "Best: S07304-GM7D-JQ93-9NHLV" in output


def test_ocr_candidates_lists_scores():
    output = ocr_candidates("S07304-GM7D-JQ93-9NHLV", card_type="PUBG")

    assert "S07304-GM7D-JQ93-9NHLV | score=" in output


def test_ocr_font_stats_reports_repository_counts(tmp_path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    repository.learn_sample("S07304-GM7D-JQ93-9NHLV", card_type="PUBG")

    output = ocr_font_stats(repository)

    assert "Profiles: 1" in output
    assert "Samples: 1" in output


def test_ocr_font_commands_list_rules_and_toggle(tmp_path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    profile = repository.learn_sample(
        "S07304-9M8Q-Y7UW-78Z2U",
        card_type="PUBG",
        error_pairs={"2>Z": 1},
        position_rules={"19:2>Z": 1},
        font_hash="pubg_font_a_supplier",
    )

    assert profile.font_hash in ocr_fonts(repository)
    assert "2>Z" in ocr_font_rules(profile.font_hash, repository)
    assert "disabled" in ocr_font_disable(profile.font_hash, repository)
    assert "enabled" in ocr_font_enable(profile.font_hash, repository)


def test_ocr_learn_debug_reports_missing_cache_and_recovered_cards(tmp_path):
    output = ocr_learn_debug(
        """
        S07304-7G8D KWXQ-6FZ2F熊533
        S07304-ZTXV-DQTN+ZJ63H熊533
        """,
        base_path=tmp_path,
    )

    assert "OCR cache: missing" in output
    assert "人工数量: 2" in output
    assert "S07304-7G8D-KWXQ-6FZ2F" in output
    assert "S07304-ZTXV-DQTN-ZJ63H" in output
