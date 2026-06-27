from pathlib import Path

import bot
import pytest


@pytest.fixture(autouse=True)
def enable_remote_ocr_for_remote_worker_tests(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_ENABLED", True)
    bot.close_remote_http_client()
    yield
    bot.close_remote_http_client()


PUBG_PREFIXES = [
    "S07304",
    "S07234",
    "S07303",
    "S07240",
    "S07292",
    "S07298",
    "S07213",
    "S07291",
    "S07205",
    "S07239",
    "S07228",
    "S07286",
]


@pytest.fixture(autouse=True)
def enable_remote_ocr_for_remote_worker_tests():
    old_enabled = bot.REMOTE_OCR_ENABLED
    old_url = bot.REMOTE_OCR_URL
    bot.REMOTE_OCR_ENABLED = True
    bot.REMOTE_OCR_URL = "http://100.81.208.104:8000"
    yield
    bot.REMOTE_OCR_ENABLED = old_enabled
    bot.REMOTE_OCR_URL = old_url


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


def test_all_pubg_prefixes_are_recognized_as_pubg_only():
    for prefix in PUBG_PREFIXES:
        text = f"{prefix}-ABCD-EFGH-IJKLM"

        assert bot.is_pubg_image_text(text) is True
        assert bot.extract_cards(text) == [text]
        assert bot.extract_psn_cards(text) == []
        assert bot.extract_psn_ordered(text) == []


def test_all_pubg_prefix_tails_are_not_psn():
    for prefix in PUBG_PREFIXES:
        text = f"{prefix}-ABCD-EFGH-IJKLM"
        tail = "ABCD-EFGH-IJKL"

        assert bot.extract_cards(text) == [text]
        assert bot.extract_psn_cards(text + "\n" + tail) == []
        assert bot.extract_psn_ordered(text + "\n" + tail) == []


def test_s07292_newline_tail_is_joined_and_psn_is_empty():
    text = "S07292-ABCD-EFGH-\nIJKLM"

    assert bot.extract_cards(text) == ["S07292-ABCD-EFGH-IJKLM"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_s07234_four_char_tail_is_pubg_trace_only():
    text = "S07234-ABCD-EFGH-IJKL"

    assert bot.extract_cards(text) == []
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_any_s07_prefix_with_five_char_tail_is_pubg():
    text = "S07999-ABCD-EFGH-IJKLM"

    assert bot.is_pubg_image_text(text) is True
    assert bot.extract_cards(text) == [text]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text, force=True) == []


def test_any_s07_prefix_tail_fragment_is_not_psn():
    text = "7999-ABCD-EFGH"

    assert bot.is_pubg_image_text(text) is True
    assert bot.extract_psn_cards(text, force=True) == []
    assert bot.extract_psn_ordered(text, force=True) == []


def test_any_missing_s0_pubg_prefix_is_repaired_when_complete():
    text = "7999-ABCD-EFGH-IJKLM"

    assert bot.extract_cards(text) == ["S07999-ABCD-EFGH-IJKLM"]
    assert bot.extract_psn_ordered(text, force=True) == []


def test_pubg_prefix_trace_without_complete_card_blocks_psn():
    text = "S07292 blur\nABCD-EFGH-IJKL"

    assert bot.is_pubg_image_text(text) is True
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_second_pubg_card_does_not_generate_psn_substring():
    text = "S07304-PQ7S-A2K5-79VQR"

    assert bot.extract_cards(text) == ["S07304-PQ7S-A2K5-79VQR"]
    assert bot.extract_psn_cards(text) == []
    assert bot.extract_psn_ordered(text) == []


def test_four_char_tail_pubg_is_not_psn():
    text = "S07304-DTUM-QWGA-CEGV"

    assert bot.extract_cards(text) == []
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

    assert bot.extract_cards(text) == []
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


def test_remote_worker_four_char_tail_pubg_trace_is_not_psn(monkeypatch, tmp_path):
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
        "S07304-38ZM-QFHZ-VKZ7M",
    )
    assert result.psn_cards == tuple()
    assert result.psn_ordered == tuple()


def test_remote_worker_uses_ordered_text_lines_for_wrapped_pubg(monkeypatch, tmp_path, caplog):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")
    payload = {
        "ok": True,
        "cards": [
            {"text": "S07304-94VF-NG88-JES07", "score": 0.99},
        ],
        "texts": [
            {"text": "卡号：S07304-94VF-NG88-", "rec_box": [20, 10, 300, 30]},
            {"text": "KLQUE", "rec_box": [20, 35, 120, 55]},
            {"text": "密码：", "rec_box": [20, 60, 100, 80]},
            {"text": "卡号：S07304-UM3A-RHGF-", "rec_box": [20, 90, 300, 110]},
            {"text": "SY5RQ", "rec_box": [20, 115, 120, 135]},
            {"text": "密码：", "rec_box": [20, 140, 100, 160]},
        ],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(payload))

    with caplog.at_level("INFO"):
        result = bot.run_remote_ocr(image_path)

    assert result is not None
    assert result.cards == (
        "S07304-94VF-NG88-KLQUE",
        "S07304-UM3A-RHGF-SY5RQ",
    )
    assert "S07304-94VF-NG88-JES07" not in result.cards
    assert result.psn_cards == tuple()
    assert result.psn_ordered == tuple()
    assert "PUBG LINE WRAP MERGED:" in caplog.text
    assert "PUBG WORKER CARD DROPPED: S07304-94VF-NG88-JES07 reason=conflict_with_line_wrap" in caplog.text


def test_wrapped_pubg_does_not_borrow_next_card_prefix(monkeypatch, tmp_path, caplog):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")
    payload = {
        "ok": True,
        "cards": [
            {"text": "S07304-94VF-NG88-JES07", "score": 0.99},
        ],
        "texts": [
            {"text": "card: S07304-94VF-NG88-", "rec_box": [20, 10, 300, 30]},
            {"text": "JE", "rec_box": [20, 35, 120, 55]},
            {"text": "card: S07304-UM3A-RHGF-", "rec_box": [20, 90, 300, 110]},
            {"text": "SY5RQ", "rec_box": [20, 115, 120, 135]},
        ],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(payload))

    with caplog.at_level("INFO"):
        result = bot.run_remote_ocr(image_path)

    assert result is not None
    assert result.cards == ("S07304-UM3A-RHGF-SY5RQ",)
    assert "S07304-94VF-NG88-JES07" not in result.cards
    assert "PUBG LINE WRAP UNRESOLVED:" in caplog.text
    assert "PUBG WORKER CARD DROPPED: S07304-94VF-NG88-JES07 reason=conflict_with_line_wrap" in caplog.text


def test_remote_worker_recovers_first_wrapped_card_and_keeps_complete_cards(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")
    payload = {
        "ok": True,
        "cards": [
            {"text": "S07304-PZA2-THGH-LPAAZ", "score": 0.99},
            {"text": "S07304-CDRC-ULTQ-T6JZP", "score": 0.99},
        ],
        "texts": [
            {"text": "卡号：S07304-EVGM-", "rec_box": [20, 10, 260, 30]},
            {"text": "PDWH-7CD7Q", "rec_box": [20, 35, 180, 55]},
            {"text": "密码：", "rec_box": [20, 60, 100, 80]},
            {"text": "卡号：S07304-PZA2-THGH-LPAAZ", "rec_box": [20, 90, 360, 110]},
            {"text": "密码：", "rec_box": [20, 115, 100, 135]},
            {"text": "卡号：S07304-CDRC-ULTQ-T6JZP", "rec_box": [20, 145, 360, 165]},
        ],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(payload))

    result = bot.run_remote_ocr(image_path)

    assert result is not None
    assert result.cards == (
        "S07304-EVGM-PDWH-7CD7Q",
        "S07304-PZA2-THGH-LPAAZ",
        "S07304-CDRC-ULTQ-T6JZP",
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


def test_pubg_prefix_tail_does_not_become_psn():
    text = "7292-P67A-CX6E"

    assert bot.is_pubg_image_text(text) is True
    assert bot.extract_psn_ordered(text, force=True) == []
    assert bot.extract_psn_cards(text, force=True) == []


def test_pubg_missing_s0_prefix_is_repaired_when_complete():
    text = "7292-P67A-CX6E-RZUN6"

    assert bot.extract_cards(text) == ["S07292-P67A-CX6E-RZUN6"]
    assert bot.extract_psn_ordered(text, force=True) == []


def test_s07_pubg_requires_five_char_tail():
    incomplete = "S07292-XTLV-W93R-5P55"
    complete = "S07292-XTLV-W93R-5P55S"

    assert bot.extract_cards(incomplete) == []
    assert bot.extract_psn_ordered(incomplete, force=True) == []
    assert bot.extract_cards(complete) == [complete]


def test_s07298_prefix_is_valid_pubg():
    assert bot.extract_cards("S07298-SF9Y-BEYJ-PXYHZ") == ["S07298-SF9Y-BEYJ-PXYHZ"]
    assert bot.extract_cards("S07298-YH8G-HJT3-KQ2L3") == ["S07298-YH8G-HJT3-KQ2L3"]
    assert bot.extract_psn_ordered("S07298-SF9Y-BEYJ-PXYHZ", force=True) == []


def test_remote_worker_pubg_tail_fragment_does_not_output_psn(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")
    payload = {
        "ok": True,
        "cards": [{"text": "7292-P67A-CX6E", "score": 0.99}],
        "texts": [{"text": "7292-P67A-CX6E", "score": 0.99}],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(payload))

    result = bot.run_remote_ocr(image_path)

    assert result is None
