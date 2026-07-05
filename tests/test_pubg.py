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


def test_pubg_line_wrap_rejects_overlong_tail_without_guessing():
    text = "卡号：S07336-9R6P-VERQ-\nVTZRFEXTRA"

    cards, unresolved = bot.extract_cards_from_ordered_lines(bot.ordered_ocr_text_lines(text.splitlines()))

    assert cards == []
    assert unresolved is True


def test_handwritten_compact_pubg_repairs_s0_and_splits_tail_only():
    assert bot.extract_cards("507336-3L9T-W338JR626") == ["S07336-3L9T-W338-JR626"]
