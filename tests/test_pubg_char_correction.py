from pathlib import Path

import bot
import pytest
from services.ocr.font_repository import FontRepository
from services.ocr.pubg_char_correction import apply_pubg_char_corrections, correct_pubg_card


@pytest.mark.parametrize(
    "card",
    [
        "S07304-WJB9-VPEZ-MUFWK",
        "S07304-RC96-Z437-QTWC9",
        "S07304-9M8Q-Y7UW-7822U",
        "S07304-GM72-JQ93-8NHLV",
        "S07304-8MP5-4TY9-VDVR6",
        "S07336-6HD2-HTP2-J6CZ9",
    ],
)
def test_one_time_card_segments_are_never_rewritten_globally(card):
    result = apply_pubg_char_corrections([card])

    assert result.cards == (card,)
    assert result.corrections == tuple()


def test_psn_is_not_changed():
    result = apply_pubg_char_corrections(["PFP7-FP8X-26PH"])

    assert result.cards == ("PFP7-FP8X-26PH",)
    assert result.corrections == tuple()


@pytest.mark.parametrize("rule_count", [1, 3, 10])
def test_unknown_font_profile_never_rewrites_card(tmp_path: Path, rule_count):
    repository = FontRepository(tmp_path / "font_profiles.json")
    repository.learn_sample(
        "S07304-TEST-AAAA-BBBBB",
        card_type="PUBG",
        error_pairs={"9>S": rule_count},
        position_rules={"10:9>S": rule_count},
        font_hash="unknown_font",
    )

    corrected, reason = correct_pubg_card(
        "S07304-WJB9-VPEZ-MUFWK",
        font_repository=repository,
    )

    assert corrected == "S07304-WJB9-VPEZ-MUFWK"
    assert reason == "unchanged"


@pytest.mark.parametrize("rule_count", [0, 1, 2])
def test_matching_font_rule_requires_three_confirmations(tmp_path: Path, rule_count):
    repository = FontRepository(tmp_path / "font_profiles.json")
    repository.learn_sample(
        "S07304-TEST-AAAA-BBBBB",
        card_type="PUBG",
        error_pairs={"9>S": rule_count},
        position_rules={"10:9>S": rule_count},
        font_hash="supplier_font_a",
    )

    corrected, reason = correct_pubg_card(
        "S07304-WJB9-VPEZ-MUFWK",
        font_repository=repository,
        font_hash="supplier_font_a",
    )

    assert corrected == "S07304-WJB9-VPEZ-MUFWK"
    assert reason == "unchanged"


def test_matching_font_rule_applies_after_three_confirmations(tmp_path: Path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    repository.learn_sample(
        "S07304-TEST-AAAA-BBBBB",
        card_type="PUBG",
        error_pairs={"9>S": 3},
        position_rules={"10:9>S": 3},
        font_hash="supplier_font_a",
    )

    corrected, reason = correct_pubg_card(
        "S07304-WJB9-VPEZ-MUFWK",
        font_repository=repository,
        font_hash="supplier_font_a",
    )

    assert corrected == "S07304-WJBS-VPEZ-MUFWK"
    assert reason == "learned_font_rule"


def test_different_font_never_uses_other_profile(tmp_path: Path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    repository.learn_sample(
        "S07304-TEST-AAAA-BBBBB",
        card_type="PUBG",
        error_pairs={"9>S": 10},
        position_rules={"10:9>S": 10},
        font_hash="supplier_font_a",
    )

    corrected, reason = correct_pubg_card(
        "S07304-WJB9-VPEZ-MUFWK",
        font_repository=repository,
        font_hash="supplier_font_b",
    )

    assert corrected == "S07304-WJB9-VPEZ-MUFWK"
    assert reason == "unchanged"


def test_disabled_matching_font_profile_never_rewrites_card(tmp_path: Path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    repository.learn_sample(
        "S07304-TEST-AAAA-BBBBB",
        card_type="PUBG",
        error_pairs={"9>S": 10},
        position_rules={"10:9>S": 10},
        font_hash="supplier_font_a",
    )
    repository.set_enabled("supplier_font_a", False)

    corrected, reason = correct_pubg_card(
        "S07304-WJB9-VPEZ-MUFWK",
        font_repository=repository,
        font_hash="supplier_font_a",
    )

    assert corrected == "S07304-WJB9-VPEZ-MUFWK"
    assert reason == "unchanged"


def test_remote_ocr_does_not_apply_historical_card_substitution(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")
    monkeypatch.setattr(bot, "REMOTE_OCR_ENABLED", True)
    monkeypatch.setattr(bot, "REMOTE_OCR_URL", "http://127.0.0.1:8000")
    bot.close_remote_http_client()

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
    bot.close_remote_http_client()

    assert result is not None
    assert result.cards == ("S07304-WJB9-VPEZ-MUFWK",)
    assert result.corrections_applied == tuple()
