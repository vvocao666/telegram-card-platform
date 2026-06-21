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
