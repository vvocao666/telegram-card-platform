from pathlib import Path

import bot
from services.ocr import psn_parser


def test_psn_parser_exports_current_functions():
    snapshot = Path("services/ocr/psn_parser.py")

    assert snapshot.exists()
    assert psn_parser.extract_psn_cards is bot.extract_psn_cards
    assert psn_parser.scan_psn_candidates is bot.scan_psn_candidates
    assert psn_parser.repair_psn_group is bot.repair_psn_group


def test_psn_parser_uses_current_bot_logic():
    cards = bot.extract_psn_cards("ABCD-EFGH-IJKL")

    assert cards == ["ABCD-EFGH-IJKL"]


def test_embedded_psn_inside_long_garbage_token_is_suppressed():
    text = "92981-848M-L674-9eEL05:\n2981-848M-L674"

    assert bot.extract_psn_cards(text, force=True) == []
    assert bot.extract_psn_ordered(text, force=True) == []


def test_independent_psn_still_outputs_when_not_embedded():
    text = "PSN\n2981-848M-L674"

    assert bot.extract_psn_cards(text, force=True) == ["2981-848M-L674"]


def test_psn_tail_starting_with_7_letter_is_not_pubg_trace():
    text = "AH5F-C63H-7LML\nGXGQ-GH68-X2PG"

    assert not bot.is_pubg_image_text(text)
    assert bot.extract_psn_cards(text) == ["AH5F-C63H-7LML", "GXGQ-GH68-X2PG"]
    assert bot.extract_psn_ordered(text) == ["AH5F-C63H-7LML", "GXGQ-GH68-X2PG"]


def test_psn_starting_with_7_and_three_digits_is_not_pubg_trace():
    text = "7654-ABCD-EFGH"

    assert not bot.is_pubg_image_text(text)
    assert bot.extract_psn_cards(text) == [text]
    assert bot.extract_psn_ordered(text) == [text]


def test_psn_first_group_wrapped_across_adjacent_ocr_lines_is_recovered():
    text = "PSN港服200港币卡密：\npsn50港币TJBD-XP8R-3GTCpsn150港币JL4\n2-LC6F-PPAB"

    assert bot.extract_psn_cards(text) == ["TJBD-XP8R-3GTC", "JL42-LC6F-PPAB"]
    assert bot.extract_psn_ordered(text) == ["TJBD-XP8R-3GTC", "JL42-LC6F-PPAB"]


def test_psn_first_group_is_not_recovered_across_unrelated_line():
    text = "JL4\n说明文字\n2-LC6F-PPAB"

    assert bot.extract_psn_cards(text, force=True) == []


def test_default_psn_limit_keeps_batches_up_to_ten():
    cards = [f"A{index:03}-BBBB-CCCC" for index in range(11)]

    assert bot.MAX_PSN_PER_IMAGE == 10
    for count in (3, 4, 5, 7, 10):
        assert bot.limit_psn_ordered(cards[:count], None) == cards[:count]
    assert bot.limit_psn_ordered(cards, None) == cards[:10]
