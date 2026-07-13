import json

import pytest

import services.runtime as runtime
from services.ocr.font_repository import FontRepository


REAL_PUBG_SAMPLE = """
S07304-WJB9-VPEZ-MUFWK
S07304-RC96-2437-QTWC9
S07304-9M8Q-Y7UW-7822U
S07304-GM7D-
JQ93-9NHLV
S07304-XFBX-EHKX-RB34D
S07304-8MP5-4TY9-VDVR6
"""


EXPECTED_PUBG_CARDS = [
    "S07304-WJB9-VPEZ-MUFWK",
    "S07304-RC96-2437-QTWC9",
    "S07304-9M8Q-Y7UW-7822U",
    "S07304-GM7D-JQ93-9NHLV",
    "S07304-XFBX-EHKX-RB34D",
    "S07304-8MP5-4TY9-VDVR6",
]


@pytest.mark.parametrize(
    "card",
    [
        "S07336-A0BC-DEFG-HJKLM",
        "S07324-AB1C-DEFG-HJKLM",
        "S07292-ABCO-DEFG-HJKLM",
        "S07304-ABCI-DEFG-HJKLM",
    ],
)
def test_all_s07_pubg_cards_reject_forbidden_body_chars(card):
    assert runtime.pubg_has_forbidden_body_chars(card)

    settled, uncertain, corrections = runtime.settle_and_correct_pubg_cards([card])

    assert settled == []
    assert uncertain == 1
    assert corrections == tuple()


def test_pubg_prefix_digits_do_not_trigger_forbidden_body_rule():
    card = "S07336-ABCD-EFGH-JKLMN"

    assert not runtime.pubg_has_forbidden_body_chars(card)
    settled, uncertain, _ = runtime.settle_and_correct_pubg_cards([card])
    assert settled == [card]
    assert uncertain == 0


def test_runtime_ocrspace_enhancement_does_not_memorize_one_time_cards(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "OCR_CANDIDATES_PATH", tmp_path / "ocr_candidates.json")
    monkeypatch.setattr(runtime, "font_repository", FontRepository(tmp_path / "ocr_font_profiles.json"))

    legacy_cards = runtime.extract_cards(REAL_PUBG_SAMPLE)
    enhanced_cards, stats = runtime.enhanced_ocrspace_pubg_cards(REAL_PUBG_SAMPLE, legacy_cards)
    settled_cards, _, corrections = runtime.settle_and_correct_pubg_cards(enhanced_cards + legacy_cards)

    assert settled_cards == EXPECTED_PUBG_CARDS
    assert corrections == tuple()
    assert len(settled_cards) / len(EXPECTED_PUBG_CARDS) == 1.0
    assert stats["ocr_fixed_count"] >= 1
    assert stats["ocr_missing_count"] >= 0
    assert stats["ocr_false_negative"] >= 0
    assert stats["ocr_character_confusion"] >= 1


def test_runtime_ocrspace_enhancement_writes_candidate_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / "ocr_candidates.json"
    monkeypatch.setattr(runtime, "OCR_CANDIDATES_PATH", audit_path)
    monkeypatch.setattr(runtime, "font_repository", FontRepository(tmp_path / "ocr_font_profiles.json"))

    runtime.enhanced_ocrspace_pubg_cards(REAL_PUBG_SAMPLE, runtime.extract_cards(REAL_PUBG_SAMPLE))
    data = json.loads(audit_path.read_text(encoding="utf-8"))

    assert data[0]["ocr_raw"] == REAL_PUBG_SAMPLE
    assert data[0]["best_candidate"] is not None
    assert data[0]["best_score"] is not None
    assert "candidate_list" in data[0]
    assert "validator_reject_reason" in data[0]
