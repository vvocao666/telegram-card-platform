from pathlib import Path

import bot
from services.ocr import pubg_parser


def test_pubg_parser_exports_current_functions():
    snapshot = Path("services/ocr/pubg_parser.py")

    assert snapshot.exists()
    assert pubg_parser.extract_cards is bot.extract_cards
    assert pubg_parser.valid_card is bot.valid_card
    assert pubg_parser.repair_first_group is bot.repair_first_group


def test_pubg_parser_uses_current_bot_logic():
    cards = bot.extract_cards("S07304-KVTE-JZGW-JVB4U")

    assert cards == ["S07304-KVTE-JZGW-JVB4U"]


def test_pubg_prefix_requires_s07_plus_three_digits():
    assert bot.valid_card("S07336-9R6P-VERQ-VTZRF")
    assert not bot.valid_card("S07ABC-9R6P-VERQ-VTZRF")


def test_pubg_line_wrap_rebuilds_adjacent_tail_segments():
    text = (
        "卡号：S07336-9R6P-VERQ-\n"
        "VTZRF\n"
        "密码：\n"
        "卡号：S07336-25DY-\n"
        "FM6W-3K8D8\n"
        "密码：\n"
        "卡号：S07336-BKBH-AAUK-\n"
        "LPJVK"
    )

    cards, unresolved = bot.extract_cards_from_ordered_lines(bot.ordered_ocr_text_lines(text.splitlines()))

    assert cards == [
        "S07336-9R6P-VERQ-VTZRF",
        "S07336-25DY-FM6W-3K8D8",
        "S07336-BKBH-AAUK-LPJVK",
    ]
    assert unresolved is False


def test_pubg_line_wrap_rebuilds_split_s073_prefix_segments():
    text = (
        "PUBG11200G币卡密： 11200G： S073\n"
        "36-NJEF-L9G8-F6Y8N\n"
        "PUBG11200G币卡密： 11200G： S073\n"
        "36-FTBJ-3SLT-PYG2H\n"
        "PUBG11200G币卡密： 11200G： S073\n"
        "36-6W23-CPJE-86A2Q\n"
        "PUBG11200G币卡密： 11200G： S073\n"
        "36-RKKC-HVSD-REBZ9"
    )

    cards, unresolved = bot.extract_cards_from_ordered_lines(bot.ordered_ocr_text_lines(text.splitlines()))

    assert cards == [
        "S07336-NJEF-L9G8-F6Y8N",
        "S07336-FTBJ-3SLT-PYG2H",
        "S07336-6W23-CPJE-86A2Q",
        "S07336-RKKC-HVSD-REBZ9",
    ]
    assert unresolved is False


def test_pubg_split_s073_prefix_requires_two_digit_tail():
    text = "PUBG11200G币卡密： 11200G： S073\nX6-NJEF-L9G8-F6Y8N"

    cards, unresolved = bot.extract_cards_from_ordered_lines(bot.ordered_ocr_text_lines(text.splitlines()))

    assert cards == []
    assert unresolved is False


def test_pubg_line_wrap_previous_tail_disabled_when_multiple_prefixes_exist():
    text = "AAAAA\nS07304-G5HC-YH9V-\nS07304-ABCD-EFGH-"

    cards, unresolved = bot.extract_cards_from_ordered_lines(bot.ordered_ocr_text_lines(text.splitlines()))

    assert cards == []
    assert unresolved is True


def test_pubg_line_wrap_prefers_visual_y_order_when_coordinates_exist():
    lines = bot.ordered_ocr_text_lines(
        [
            {"text": "QRQ7E", "rec_box": [10, 80, 100, 100]},
            {"text": "信息： 卡号： S07304-G5HC-YH9V-", "rec_box": [10, 40, 200, 60]},
        ]
    )

    cards, unresolved = bot.extract_cards_from_ordered_lines(lines)

    assert cards == ["S07304-G5HC-YH9V-QRQ7E"]
    assert unresolved is False


def test_pubg_line_wrap_rejects_overlong_tail_without_guessing():
    text = "卡号：S07336-9R6P-VERQ-\nVTZRFEXTRA"

    cards, unresolved = bot.extract_cards_from_ordered_lines(bot.ordered_ocr_text_lines(text.splitlines()))

    assert cards == []
    assert unresolved is True


def test_handwritten_compact_pubg_repairs_s0_and_splits_tail_only():
    assert bot.extract_cards("507336-3L9T-W338JR626") == ["S07336-3L9T-W338-JR626"]


def test_pubg_line_wrap_uses_previous_adjacent_tail_when_ocr_order_is_inverted():
    text = "QRQ7E\n信息： 卡号： S07304-G5HC-YH9V-\n-A6HA-OH90-TOTLOS"

    cards, unresolved = bot.extract_cards_from_ordered_lines(bot.ordered_ocr_text_lines(text.splitlines()))

    assert cards == ["S07304-G5HC-YH9V-QRQ7E"]
    assert unresolved is False


def test_pubg_line_wrap_previous_tail_must_exactly_fit_missing_length():
    text = "QRQ7EEXTRA\n信息： 卡号： S07304-G5HC-YH9V-"

    cards, unresolved = bot.extract_cards_from_ordered_lines(bot.ordered_ocr_text_lines(text.splitlines()))

    assert cards == []
    assert unresolved is False
