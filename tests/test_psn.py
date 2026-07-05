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
