from pathlib import Path

import bot


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        return FakeResponse(self.payload)


def test_pubg_card_does_not_generate_psn_substring():
    text = "S07304-KJDS-NPDD-NEUDY"

    assert bot.extract_cards(text) == ["S07304-KJDS-NPDD-NEUDY"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_second_pubg_card_does_not_generate_psn_substring():
    text = "S07304-PQ7S-A2K5-79VQR"

    assert bot.extract_cards(text) == ["S07304-PQ7S-A2K5-79VQR"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_labeled_pubg_tail_is_not_psn():
    text = "密码1: S07304-KJDS-NPDD-NEUDY"

    assert bot.extract_cards(text) == ["S07304-KJDS-NPDD-NEUDY"]
    assert bot.extract_psn_ordered(text) == []


def test_independent_psn_still_works():
    text = "S07304-KJDS-NPDD-NEUDY\nPFP7-FP8X-26PH"

    assert bot.extract_cards(text) == ["S07304-KJDS-NPDD-NEUDY"]
    assert bot.extract_psn_cards(text) == ["PFP7-FP8X-26PH"]
    assert bot.extract_psn_ordered(text) == ["PFP7-FP8X-26PH"]


def test_remote_worker_pubg_substring_psn_is_filtered(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")
    payload = {
        "ok": True,
        "cards": [
            {"text": "S07304-KJDS-NPDD-NEUDY", "score": 0.99},
            {"text": "KJDS-NPDD-NEUD", "score": 0.98},
        ],
        "texts": [{"text": "S07304-KJDS-NPDD-NEUDY", "score": 0.99}],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(payload))

    result = bot.run_remote_ocr(image_path)

    assert result is not None
    assert result.cards == ("S07304-KJDS-NPDD-NEUDY",)
    assert result.psn_cards == tuple()
    assert result.psn_ordered == tuple()


def test_format_reply_filters_existing_dirty_psn():
    result = bot.OcrResult(
        cards=("S07304-KJDS-NPDD-NEUDY",),
        psn_cards=("KJDS-NPDD-NEUD",),
        psn_ordered=("KJDS-NPDD-NEUD",),
    )

    reply = bot.format_reply([result])

    assert "S07304-KJDS-NPDD-NEUDY" in reply
    assert "PSN" not in reply
