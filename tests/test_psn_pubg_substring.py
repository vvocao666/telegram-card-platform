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


def test_four_char_tail_pubg_is_not_psn():
    text = "S07304-DTUM-QWGA-CEGV"

    assert bot.extract_cards(text) == ["S07304-DTUM-QWGA-CEGV"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_whrl_pubg_is_not_psn():
    text = "S07304-WHRL-F8YT-7RYRQ"

    assert bot.extract_cards(text) == ["S07304-WHRL-F8YT-7RYRQ"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_38zm_pubg_is_not_psn():
    text = "S07304-38ZM-QFHZ-VKZ7M"

    assert bot.extract_cards(text) == ["S07304-38ZM-QFHZ-VKZ7M"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_s07_line_is_not_scanned_as_psn():
    text = "card: S07304-DTUM-QWGA-CEGV"

    assert bot.extract_cards(text) == ["S07304-DTUM-QWGA-CEGV"]
    assert bot.scan_psn_candidates(text) == []


def test_labeled_pubg_tail_is_not_psn():
    text = "密码1: S07304-KJDS-NPDD-NEUDY"

    assert bot.extract_cards(text) == ["S07304-KJDS-NPDD-NEUDY"]
    assert bot.extract_psn_ordered(text) == []


def test_same_image_with_pubg_trace_suppresses_psn():
    text = "S07304-KJDS-NPDD-NEUDY\nPFP7-FP8X-26PH"

    assert bot.extract_cards(text) == ["S07304-KJDS-NPDD-NEUDY"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_independent_psn_image_still_works():
    text = "PFP7-FP8X-26PH"

    assert bot.extract_cards(text) == []
    assert bot.extract_psn_cards(text) == ["PFP7-FP8X-26PH"]
    assert bot.extract_psn_ordered(text) == ["PFP7-FP8X-26PH"]


def test_pubg_image_trace_without_valid_pubg_does_not_emit_psn():
    text = "S07 blur\nDTUM-QWGA-CEGV"

    assert bot.is_pubg_image_text(text) is True
    assert bot.extract_cards(text) == []
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_pubg_newline_tail_is_joined_and_psn_is_empty():
    text = "S07304-EVGM-\nPDWH-7CD7Q"

    assert bot.extract_cards(text) == ["S07304-EVGM-PDWH-7CD7Q"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_pubg_newline_last_group_is_joined_and_psn_is_empty():
    text = "S07304-94VF-NG88-\nKLQUE"

    assert bot.extract_cards(text) == ["S07304-94VF-NG88-KLQUE"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_pubg_image_never_outputs_both_pubg_and_psn():
    result = bot.OcrResult(
        cards=tuple(bot.extract_cards("S07304-W4CW-6ZC8-DRN2R\nW4CW-6ZC8-DRN")),
        psn_ordered=tuple(bot.extract_psn_ordered("S07304-W4CW-6ZC8-DRN2R\nW4CW-6ZC8-DRN")),
    )

    assert result.cards == ("S07304-W4CW-6ZC8-DRN2R",)
    assert result.psn_ordered == tuple()


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


def test_remote_worker_four_char_tail_pubg_is_not_psn(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")
    payload = {
        "ok": True,
        "cards": [
            {"text": "S07304-WHRL-F8YT-7RYRQ", "score": 0.99},
            {"text": "S07304-DTUM-QWGA-CEGV", "score": 0.99},
            {"text": "S07304-38ZM-QFHZ-VKZ7M", "score": 0.99},
            {"text": "DTUM-QWGA-CEGV", "score": 0.98},
        ],
        "texts": [
            {"text": "S07304-WHRL-F8YT-7RYRQ", "score": 0.99},
            {"text": "S07304-DTUM-QWGA-CEGV", "score": 0.99},
            {"text": "S07304-38ZM-QFHZ-VKZ7M", "score": 0.99},
        ],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(payload))

    result = bot.run_remote_ocr(image_path)

    assert result is not None
    assert result.cards == (
        "S07304-WHRL-F8YT-7RYRQ",
        "S07304-DTUM-QWGA-CEGV",
        "S07304-38ZM-QFHZ-VKZ7M",
    )
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
