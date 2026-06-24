from pathlib import Path

import bot
import pytest
from services.ocr.font_repository import FontRepository
from services.ocr.pubg_char_correction import apply_pubg_char_corrections, correct_pubg_card


@pytest.fixture(autouse=True)
def enable_remote_ocr_for_remote_tests():
    old_enabled = bot.REMOTE_OCR_ENABLED
    old_url = bot.REMOTE_OCR_URL
    bot.REMOTE_OCR_ENABLED = True
    bot.REMOTE_OCR_URL = "http://100.81.208.104:8000"
    yield
    bot.REMOTE_OCR_ENABLED = old_enabled
    bot.REMOTE_OCR_URL = old_url


def test_wjb9_corrects_to_wjbs():
    corrected, reason = correct_pubg_card("S07304-WJB9-VPEZ-MUFWK")

    assert corrected == "S07304-WJBS-VPEZ-MUFWK"
    assert reason == "safe_known_segment_rule"


def test_rc96_and_z437_correct_to_rcs6_and_2437():
    corrected, reason = correct_pubg_card("S07304-RC96-Z437-QTWC9")

    assert corrected == "S07304-RCS6-2437-QTWC9"
    assert reason == "safe_known_segment_rule"


def test_7822u_corrects_to_78z2u():
    corrected, reason = correct_pubg_card("S07304-9M8Q-Y7UW-7822U")

    assert corrected == "S07304-9M8Q-Y7UW-78Z2U"
    assert reason == "safe_known_segment_rule"


def test_jq93_corrects_to_jqs3():
    corrected, reason = correct_pubg_card("S07304-GM72-JQ93-8NHLV")

    assert corrected == "S07304-GM72-JQS3-8NHLV"
    assert reason == "safe_known_segment_rule"


def test_4ty9_corrects_to_4tys():
    corrected, reason = correct_pubg_card("S07304-8MP5-4TY9-VDVR6")

    assert corrected == "S07304-8MP5-4TYS-VDVR6"
    assert reason == "safe_known_segment_rule"


def test_psn_is_not_changed():
    result = apply_pubg_char_corrections(["PFP7-FP8X-26PH"])

    assert result.cards == ("PFP7-FP8X-26PH",)
    assert result.corrections == tuple()


def test_without_rule_does_not_aggressively_change():
    corrected, reason = correct_pubg_card("S07304-ABCD-EFGH-IJKLM")

    assert corrected == "S07304-ABCD-EFGH-IJKLM"
    assert reason == "unchanged"


def test_learned_position_rule_applies_for_same_font(tmp_path: Path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    repository.learn_sample(
        "S07304-TEST-AAAA-BBBBB",
        card_type="PUBG",
        error_pairs={"9>S": 1},
        position_rules={"10:9>S": 1},
        font_hash="unknown_font",
    )

    corrected, reason = correct_pubg_card("S07304-WJB9-VPEZ-MUFWK", font_repository=repository)

    assert corrected == "S07304-WJBS-VPEZ-MUFWK"
    assert reason == "learned_font_rule"


def test_remote_ocr_returns_corrections_debug(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "ok": True,
                "cards": [{"text": "S07304-WJB9-VPEZ-MUFWK", "score": 0.99}],
                "texts": [{"text": "S07304-WJB9-VPEZ-MUFWK", "score": 0.99}],
            }

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient())

    result = bot.run_remote_ocr(image_path)

    assert result is not None
    assert result.cards == ("S07304-WJBS-VPEZ-MUFWK",)
    assert result.corrections_applied == (
        {"from": "S07304-WJB9-VPEZ-MUFWK", "to": "S07304-WJBS-VPEZ-MUFWK", "reason": "safe_known_segment_rule"},
    )
