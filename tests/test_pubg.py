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
