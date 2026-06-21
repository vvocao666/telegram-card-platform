import json

from services.ocr.learning_commands import build_learning_preview, execute_learning, format_learning_stats
from services.ocr.today_cache import append_today_ocr_cache


HUMAN_TEXT = """
S07304-AAAA-BBBB-CCCCC 微信小碗 515
S07304-DDDD-EEEE-FFFFF 淘 538
S07304-1111-2222-33333
S07304-4444-5555-66666
S07304-7777-8888-99999
"""


def test_learn_cards_preview_requires_today_cache(tmp_path):
    preview = build_learning_preview(HUMAN_TEXT, base_path=tmp_path)

    assert not preview.ocr_cache_found
    assert preview.card_count == 5
    assert "OCR" in preview.message


def test_learn_cards_preview_detects_five_cards_with_cache(tmp_path):
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")

    preview = build_learning_preview(HUMAN_TEXT, base_path=tmp_path)

    assert preview.ocr_cache_found
    assert preview.card_count == 5
    assert preview.preview_cards[0] == "S07304-AAAA-BBBB-CCCCC"
    assert "/learn_confirm" in preview.message
    assert "/learn_cancel" in preview.message


def test_execute_learning_report_uses_cache_intersection(tmp_path):
    append_today_ocr_cache(
        [
            "S07304-AAAA-BBBB-CCCCC",
            "S07304-DDDD-EEEE-FFFFG",
            "S07304-ZZZZ-ZZZZ-ZZZZZ",
        ],
        path=tmp_path / "outputs" / "today_ocr_cache.json",
    )

    output = execute_learning(HUMAN_TEXT, base_path=tmp_path)

    assert "OCR" in output
    assert "TOP10" in output
    assert "outputs/today_ocr_cache.json" in output
    assert "5" in output
    assert "3" in output
    assert "4" in output
    assert "2" in output


def test_learning_stats_outputs_totals(tmp_path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "font_profiles.json").write_text(
        json.dumps(
            {
                "font_a": {
                    "font_hash": "font_a",
                    "card_type": "PUBG",
                    "source_chat_id": None,
                    "source_user_id": None,
                    "sample_count": 2,
                    "error_pairs": {"2>Z": 2, "missing:S07304-AAAA-BBBB-CCCCC": 1},
                    "position_rules": {"19:2>Z": 2},
                    "confidence": 0.9,
                    "last_seen": "2026-06-22T00:00:00+00:00",
                    "enabled": True,
                }
            }
        ),
        encoding="utf-8",
    )

    output = format_learning_stats(base_path=tmp_path)

    assert "OCR Learning Stats" in output
    assert "TOP10" in output
    assert "2 -> Z" in output
    assert "S07304-AAAA-BBBB-CCCCC" in output
    assert "2026-06-22T00:00:00+00:00" in output
