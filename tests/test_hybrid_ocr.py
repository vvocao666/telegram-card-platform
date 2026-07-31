from pathlib import Path

import asyncio
import bot
import httpx
import pytest
from PIL import Image
from types import SimpleNamespace


@pytest.fixture(autouse=True)
def reset_remote_ocr_status(monkeypatch):
    old_remote_url = bot.REMOTE_OCR_URL
    monkeypatch.setattr(bot, "REMOTE_OCR_ENABLED", True)
    monkeypatch.setattr(bot, "REMOTE_OCR_URL", "http://remote.test:8000")
    bot.close_remote_http_client()
    bot.remote_ocr_status.update(
        {
            "last_ok": False,
            "last_error": "",
            "last_latency_ms": 0,
            "last_card_count": 0,
            "last_checked_at": "",
            "remote_health": False,
            "last_success_at": "",
            "last_failed_at": "",
            "today_date": "",
            "today_remote_calls": 0,
            "today_remote_success": 0,
            "today_remote_failed": 0,
            "today_fallback_count": 0,
            "today_remote_latency_total_ms": 0,
            "today_enhanced_used": 0,
            "today_cache_hits": 0,
        }
    )
    bot.remote_ocr_health_cache.update({"checked_at": 0.0, "result": None})
    bot.remote_ocr_offline_until = 0.0
    yield
    bot.close_remote_http_client()
    bot.REMOTE_OCR_URL = old_remote_url
    bot.remote_ocr_offline_until = 0.0


def test_remote_ocr_can_be_disabled_for_cloud_deploy(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "REMOTE_OCR_ENABLED", False)

    result = bot.run_remote_ocr(write_image(tmp_path))
    available, reason = bot.remote_ocr_available()

    assert result is None
    assert available is False
    assert reason == "disabled"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=None):
        self.status_code = status_code
        self.payload = payload or {}
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class FakeClient:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        return self.response

    def get(self, *args, **kwargs):
        return self.response


def write_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"fake-image")
    return image_path


def test_remote_ocr_success_returns_valid_cards(monkeypatch, tmp_path):
    payload = {
        "ok": True,
        "cards": [{"text": "S07304-WJB9-VPEZ-MUFWK", "score": 0.99}],
        "texts": [{"text": "S07304-WJB9-VPEZ-MUFWK", "score": 0.99}],
        "enhanced_used": True,
        "cached": True,
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is not None
    assert result.cards == ("S07304-WJB9-VPEZ-MUFWK",)
    assert result.corrections_applied == tuple()
    assert bot.remote_ocr_status["last_ok"] is True
    assert bot.remote_ocr_status["today_remote_calls"] == 1
    assert bot.remote_ocr_status["today_remote_success"] == 1
    assert bot.remote_ocr_status["today_remote_failed"] == 0
    assert bot.remote_ocr_status["today_enhanced_used"] == 1
    assert bot.remote_ocr_status["today_cache_hits"] == 1
    assert bot.avg_remote_latency_ms() >= 0


def test_remote_ocr_duplicate_complete_lines_count_as_one_card_slot(monkeypatch, tmp_path):
    card = "S07336-Z483-CNEE-W6C5W"
    payload = {
        "ok": True,
        "cards": [{"text": card, "score": 0.99}],
        "texts": [
            {"text": f"{card}|复制", "score": 0.99, "box": [10, 10, 260, 36]},
            {"text": f"{card}|复制", "score": 0.99, "box": [10, 48, 260, 74]},
        ],
    }
    monkeypatch.setattr(
        bot.httpx,
        "Client",
        lambda timeout: FakeClient(FakeResponse(payload=payload)),
    )

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is not None
    assert result.cards == (card,)
    assert result.pubg_expected_count == 1
    assert bot.remote_needs_ocrspace_complement(result) == (False, "")


def test_remote_ordered_rebuild_clears_worker_line_parser_warning(monkeypatch, tmp_path):
    cards = (
        "S07304-XT3D-WWCZ-7DGQZ",
        "S07304-C8EB-3NNY-2RX9S",
        "S07304-ST8J-9WHF-KLUXL",
    )
    payload = {
        "ok": True,
        "cards": [],
        "texts": [
            {"text": "CDK:S07304-XT3D-", "score": 0.97, "box": [0, 33, 242, 61]},
            {"text": "WWCZ-7DGQZ", "score": 0.99, "box": [0, 65, 170, 97]},
            {"text": "CDK:S07304-", "score": 0.98, "box": [0, 104, 173, 133]},
            {"text": "C8EB-3NNY-2RX9S", "score": 0.97, "box": [0, 137, 224, 168]},
            {"text": "CDK:S07304-ST8J-9WHF-", "score": 0.96, "box": [0, 170, 316, 204]},
            {"text": "KLUXL", "score": 0.99, "box": [0, 211, 78, 241]},
        ],
        "cpu_ocr": {
            "enabled": True,
            "shadow_only": False,
            "can_affect_result": True,
            "confirmation_mode": "strict",
            "review_required": True,
            "review_reasons": ["pubg_marker_without_valid_card"],
        },
    }
    monkeypatch.setattr(
        bot.httpx,
        "Client",
        lambda timeout: FakeClient(FakeResponse(payload=payload)),
    )

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is not None
    assert result.cards == cards
    assert result.remote_cpu_review_required is False
    assert result.has_unresolved_pubg_fragment is False
    assert bot.remote_needs_ocrspace_complement(result) == (False, "")


def test_remote_ocr_preserves_original_and_enhanced_card_evidence(monkeypatch, tmp_path):
    original = "S07336-9L9E-W6T6-FKECC"
    enhanced = "S07336-9L9E-W6T6-FKECQ"
    payload = {
        "ok": True,
        "cards": [{"text": original, "score": 0.9963}],
        "texts": [{"text": original, "score": 0.9963}],
        "ocr_original": {"cards": [{"text": original, "score": 0.9963}]},
        "ocr_enhanced": {"cards": [{"text": enhanced, "score": 0.9998}]},
    }
    monkeypatch.setattr(
        bot.httpx,
        "Client",
        lambda timeout: FakeClient(FakeResponse(payload=payload)),
    )

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is not None
    assert result.remote_variant_conflict is True
    assert result.remote_original_card_scores == ((original, 0.9963),)
    assert result.remote_enhanced_card_scores == ((enhanced, 0.9998),)
    assert result.has_unresolved_pubg_fragment is True


def test_remote_ocr_counts_each_ordered_pubg_anchor_even_when_last_tail_is_missing(monkeypatch, tmp_path):
    payload = {
        "ok": True,
        "cards": [],
        "texts": [
            {"text": "卡号：S07336-6WPM-2UY8-", "score": 0.99},
            {"text": "TL6GT", "score": 0.99},
            {"text": "卡号：S07336-", "score": 0.99},
            {"text": "YVCK-3DN9-7H92X", "score": 0.99},
            {"text": "卡号：S07336-5EC8-FVFG-", "score": 0.99},
        ],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is not None
    assert result.cards == (
        "S07336-6WPM-2UY8-TL6GT",
        "S07336-YVCK-3DN9-7H92X",
    )
    assert result.pubg_expected_count == 3
    assert bot.remote_needs_ocrspace_complement(result)[0] is True


def test_remote_ocr_recovers_single_prefix_digit_by_same_image_consensus(monkeypatch, tmp_path):
    payload = {
        "ok": True,
        "cards": [],
        "texts": [
            {"text": "S07336-ZEBT-JFGP-KR4YE", "score": 0.99},
            {"text": "S01336-3SRE-ETDS-QEXR7", "score": 0.99},
            {"text": "S07336-BHSN-T4TA-CH39R", "score": 0.99},
        ],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is not None
    assert result.cards == (
        "S07336-ZEBT-JFGP-KR4YE",
        "S07336-3SRE-ETDS-QEXR7",
        "S07336-BHSN-T4TA-CH39R",
    )


def test_remote_ocr_empty_cards_falls_back(monkeypatch, tmp_path):
    payload = {"ok": True, "cards": [], "texts": [{"text": "nothing", "score": 0.9}]}
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is None
    assert bot.remote_ocr_status["last_ok"] is False
    assert bot.remote_ocr_status["last_error"] == "no valid cards"
    assert bot.remote_ocr_status["today_remote_calls"] == 1
    assert bot.remote_ocr_status["today_remote_failed"] == 1


def test_remote_ocr_forbidden_pubg_body_chars_fall_back(monkeypatch, tmp_path):
    payload = {
        "ok": True,
        "cards": [{"text": "S07336-6HD2-HTP2-O6CZ9", "score": 0.99}],
        "texts": [{"text": "S07336-6HD2-HTP2-O6CZ9", "score": 0.99}],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is None
    assert bot.remote_ocr_status["last_ok"] is False
    assert bot.remote_ocr_status["last_error"] == "no valid cards"


def test_remote_ocr_rebuilds_from_texts_when_worker_cards_are_empty(monkeypatch, tmp_path):
    payload = {
        "ok": True,
        "cards": [],
        "texts": [
            {"text": "S07336-XAN8-2NDZ-", "score": 0.99},
            {"text": "HU6Q3 复制密码", "score": 0.99},
            {"text": "S07336-CE9Z-K74V-H", "score": 0.99},
            {"text": "XYP3 复制密码", "score": 0.99},
            {"text": "S07336-ZSNH-V8AP-", "score": 0.99},
            {"text": "TG9EP 复制密码", "score": 0.99},
        ],
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is not None
    assert result.cards == (
        "S07336-XAN8-2NDZ-HU6Q3",
        "S07336-CE9Z-K74V-HXYP3",
        "S07336-ZSNH-V8AP-TG9EP",
    )
    assert bot.remote_ocr_status["last_ok"] is True
    assert bot.remote_ocr_status["today_remote_success"] == 1
    assert bot.remote_ocr_status["today_remote_failed"] == 0


def test_remote_ocr_invalid_json_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(
        bot.httpx,
        "Client",
        lambda timeout: FakeClient(FakeResponse(json_error=ValueError("bad json"))),
    )

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is None
    assert bot.remote_ocr_status["last_ok"] is False
    assert bot.remote_ocr_status["last_error"] == "ValueError"
    assert bot.remote_ocr_status["today_remote_failed"] == 1


def test_remote_ocr_connection_failure_opens_circuit(monkeypatch, tmp_path):
    calls = {"post": 0}

    class FailingClient:
        def post(self, *args, **kwargs):
            calls["post"] += 1
            raise TimeoutError("offline")

    monkeypatch.setattr(bot, "REMOTE_OCR_OFFLINE_SECONDS", 60)
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FailingClient())

    first = bot.run_remote_ocr(write_image(tmp_path))
    second = bot.run_remote_ocr(write_image(tmp_path))

    assert first is None
    assert second is None
    assert calls["post"] == 1
    assert bot.remote_ocr_is_circuit_open()
    assert bot.remote_ocr_status["today_remote_failed"] == 1
    assert bot.remote_ocr_fallback_reason().startswith("remote offline")


def test_remote_busy_status_does_not_open_offline_circuit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        bot,
        "LOCAL_HYBRID_FLAGS",
        SimpleNamespace(worker_queue_v2=False, busy_offline_separation=True),
    )
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(status_code=429)))

    assert bot.run_remote_ocr(write_image(tmp_path)) is None
    assert not bot.remote_ocr_is_circuit_open()
    assert bot.remote_ocr_status["today_remote_busy"] == 1


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_remote_queue_transport_error_does_not_poison_remaining_batch(
    monkeypatch, tmp_path, error_type
):
    calls = {"post": 0}

    class BusyClient:
        def post(self, *args, **kwargs):
            calls["post"] += 1
            raise error_type("worker busy")

    monkeypatch.setattr(
        bot,
        "LOCAL_HYBRID_FLAGS",
        SimpleNamespace(worker_queue_v2=False, busy_offline_separation=True),
    )
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: BusyClient())

    assert bot.run_remote_ocr(write_image(tmp_path)) is None
    assert bot.run_remote_ocr(write_image(tmp_path)) is None

    assert calls["post"] == 2
    assert not bot.remote_ocr_is_circuit_open()
    assert bot.remote_ocr_status["today_remote_busy"] == 2
    assert bot.remote_ocr_status["today_remote_failed"] == 0


def test_remote_ocr_health_probe_recovers_circuit(monkeypatch):
    payload = {"ok": True, "gpu": True, "engine": "paddlex_ocr"}
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))
    bot.mark_remote_ocr_offline("TimeoutError")

    available, reason = bot.remote_ocr_available(force_probe=True)

    assert available is True
    assert reason == "ok"
    assert bot.remote_ocr_is_circuit_open() is False


def test_run_ocr_uses_remote_before_ocrspace(monkeypatch, tmp_path):
    expected = bot.OcrResult(cards=("S07304-WJB9-VPEZ-MUFWK",), raw_text="remote")
    monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: expected)
    monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unused")))

    result = bot.run_ocr(write_image(tmp_path))

    assert result is expected


def test_run_ocr_does_not_allow_cloud_to_overwrite_remote_thin_strip_conflict(
    monkeypatch, tmp_path
):
    image_path = tmp_path / "thin.jpg"
    Image.new("RGB", (500, 80), "white").save(image_path)
    remote = bot.OcrResult(
        cards=("S07324-N4RB-3744-V3Y8N",),
        raw_text="S07324-N4RB-3744-V3Y8N",
    )
    cloud = bot.OcrResult(
        cards=("S07324-N4RB-3744-V3Y8M",),
        raw_text="S07324-N4RB-3744-V3Y8M",
    )
    monkeypatch.setattr(bot, "OCR_PROVIDER", "ocrspace")
    monkeypatch.setattr(bot, "OCR_SPACE_API_KEYS", ["key"])
    remote_calls = iter((remote, remote))
    cloud_calls = iter((cloud, cloud))
    monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: next(remote_calls))
    monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: next(cloud_calls))

    result = bot.run_ocr(image_path)

    assert result.cards == ()
    assert result.uncertain_count == 1
    assert "[REMOTE]" in result.raw_text
    assert "[OCRSPACE]" in result.raw_text


def test_run_ocr_uses_fast_path_for_duplicate_remote_text_variants(monkeypatch, tmp_path, caplog):
    expected = bot.OcrResult(
        cards=("S07336-9R6P-VERQ-VTZRF",),
        raw_text=(
            "S07336-9R6P-VERQ-VTZRF\n"
            "S07336-9R6P-VERQ-VTZRF"
        ),
    )
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: expected)
    monkeypatch.setattr(
        bot,
        "run_ocrspace",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    with caplog.at_level("INFO", logger="telegram-card-platform"):
        result = bot.run_ocr(write_image(tmp_path))

    assert result is expected
    assert "OCR FAST PATH provider=remote cards=1 psn=0 markers=1" in caplog.text


def test_run_ocr_falls_back_to_ocrspace_when_remote_fails(monkeypatch, tmp_path):
    fallback = bot.OcrResult(cards=("S07304-RC96-2437-QTWC9",), raw_text="ocrspace")
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    old_verify = bot.VERIFY_WITH_LOCAL
    old_complement = bot.LOCAL_COMPLEMENT
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        bot.VERIFY_WITH_LOCAL = False
        bot.LOCAL_COMPLEMENT = False
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: None)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        result = bot.run_ocr(write_image(tmp_path))

        assert result is fallback
        assert bot.remote_ocr_status["today_fallback_count"] == 1
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys
        bot.VERIFY_WITH_LOCAL = old_verify
        bot.LOCAL_COMPLEMENT = old_complement


def test_run_ocr_uses_ocrspace_before_local_when_remote_is_offline(monkeypatch, tmp_path):
    fallback = bot.OcrResult(cards=("S07304-XVVB-EB4F-JRDTC",), raw_text="ocrspace")
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    old_local_fallback = bot.LOCAL_FALLBACK
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        bot.LOCAL_FALLBACK = True
        bot.mark_remote_ocr_offline("ConnectTimeout")
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: None)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)
        monkeypatch.setattr(bot, "run_local_ocr", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unused")))

        result = bot.run_ocr(write_image(tmp_path))

        assert result is fallback
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys
        bot.LOCAL_FALLBACK = old_local_fallback
        bot.remote_ocr_offline_until = 0.0


def test_run_ocr_complements_remote_when_pubg_fragment_unresolved(monkeypatch, tmp_path):
    remote = bot.OcrResult(
        cards=("S07304-PZA2-THGH-LPAAZ", "S07304-CDRC-ULTQ-T6JZP"),
        raw_text="S07304-EVGM-\n/H-7CD7Q\nS07304-PZA2-THGH-LPAAZ\nS07304-CDRC-ULTQ-T6JZP",
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(
        cards=("S07304-EVGM-PDWH-7CD7Q", "S07304-PZA2-THGH-LPAAZ", "S07304-CDRC-ULTQ-T6JZP"),
        raw_text="S07304-EVGM-PDWH-7CD7Q\nS07304-PZA2-THGH-LPAAZ\nS07304-CDRC-ULTQ-T6JZP",
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == (
            "S07304-EVGM-PDWH-7CD7Q",
            "S07304-PZA2-THGH-LPAAZ",
            "S07304-CDRC-ULTQ-T6JZP",
        )
        assert result.psn_cards == tuple()
        assert "[REMOTE]" in result.raw_text
        assert "[OCRSPACE]" in result.raw_text
        assert bot.remote_ocr_status["today_fallback_count"] == 1
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_remote_complement_needed_when_pubg_markers_exceed_cards(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    remote = bot.OcrResult(
        cards=("S07336-9R6P-VERQ-VTZRF", "S07336-25DY-FM6W-3K8D8"),
        raw_text=(
            "卡号：S07336-9R6P-VERQ-\n"
            "VTZRF\n"
            "卡号：S07336-25DY-\n"
            "FM6W-3K8D8\n"
            "卡号：S07336-BKBH-AAUK-\n"
            "LPJVK"
        ),
    )

    assert bot.remote_needs_ocrspace_complement(remote) == (
        True,
        "remote pubg marker count mismatch",
    )


def test_remote_complement_not_needed_when_pubg_markers_match_cards(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    remote = bot.OcrResult(
        cards=("S07336-9R6P-VERQ-VTZRF",),
        raw_text="卡号：S07336-9R6P-VERQ-\nVTZRF",
    )

    assert bot.remote_needs_ocrspace_complement(remote) == (False, "")


def test_remote_expected_count_triggers_complement_when_last_tail_was_cropped(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    remote = bot.OcrResult(
        cards=(
            "S07336-6WPM-2UY8-TL6GT",
            "S07336-YVCK-3DN9-7H92X",
        ),
        raw_text=(
            "卡号：S07336-6WPM-2UY8-\nTL6GT\n"
            "卡号：S07336-\nYVCK-3DN9-7H92X\n"
            "卡号：S07336-5EC8-FVFG-"
        ),
        pubg_expected_count=3,
    )

    assert bot.remote_needs_ocrspace_complement(remote) == (
        True,
        "remote pubg marker count mismatch",
    )


def test_duplicate_remote_text_variants_count_as_one_pubg_marker(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    remote = bot.OcrResult(
        cards=("S07336-9R6P-VERQ-VTZRF",),
        raw_text=(
            "S07336-9R6P-VERQ-VTZRF\n"
            "S07336-9R6P-VERQ-VTZRF"
        ),
    )

    assert bot.count_pubg_markers(remote.raw_text) == 1
    assert bot.remote_needs_ocrspace_complement(remote) == (False, "")


def test_full_and_wrapped_remote_variants_count_as_one_pubg_marker(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    remote = bot.OcrResult(
        cards=("S07336-9R6P-VERQ-VTZRF",),
        raw_text=(
            "S07336-9R6P-VERQ-VTZRF\n"
            "S07336-9R6P-VERQ-\n"
            "VTZRF"
        ),
    )

    assert bot.count_pubg_markers(remote.raw_text) == 1
    assert bot.remote_needs_ocrspace_complement(remote) == (False, "")


def test_conflicting_tail_variants_for_one_card_slot_count_once(monkeypatch):
    """Original/enhanced OCR tail disagreement is not a second physical card."""
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    remote = bot.OcrResult(
        cards=("S07336-TPM2-RZ9J-HCTBS",),
        raw_text=(
            "S07336-TPM2-RZ9J-HCTBS\n"
            "S07336-TPM2-RZ9J-VICTBS"
        ),
    )

    assert bot.count_pubg_markers(remote.raw_text) == 1
    assert bot.remote_needs_ocrspace_complement(remote) == (False, "")


def test_same_slot_conflicting_tails_do_not_trigger_manual_review(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    remote = bot.OcrResult(
        cards=("S07336-TPM2-RZ9J-HCTBS",),
        raw_text=(
            "S07336-TPM2-RZ9J-HCTBS\n"
            "S07336-TPM2-RZ9J-VICTBS"
        ),
    )

    assert bot.merge_pubg_expected_count(None, remote.raw_text) == 1
    assert bot.remote_needs_ocrspace_complement(remote) == (False, "")


def test_duplicate_wrapped_multi_card_sources_count_physical_slots_once():
    raw_text = (
        "S07336-DQTE-\n"
        "ZZUR-N4LZB\n"
        "S07336-\n"
        "MDUU-2URB-29U8X\n"
        "S07336-DQTE-\n"
        "ZZUR-N4LZB\n"
        "S07336-\n"
        "MDUU-2URB-29U8X"
    )

    assert bot.count_pubg_markers(raw_text) == 2
    assert bot.merge_pubg_expected_count(None, raw_text) == 2


def test_unresolved_extra_wrapped_marker_still_counts_for_review():
    raw_text = (
        "S07336-DQTE-\n"
        "ZZUR-N4LZB\n"
        "S07336-\n"
        "MDUU-2URB-29U8X\n"
        "S07336-"
    )

    assert bot.count_pubg_markers(raw_text) == 3


def test_distinct_pubg_markers_still_trigger_missing_card_complement(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
    remote = bot.OcrResult(
        cards=("S07336-9R6P-VERQ-VTZRF",),
        raw_text=(
            "S07336-9R6P-VERQ-VTZRF\n"
            "S07336-25DY-FM6W-3K8D8"
        ),
    )

    assert bot.count_pubg_markers(remote.raw_text) == 2
    assert bot.remote_needs_ocrspace_complement(remote) == (
        True,
        "remote pubg marker count mismatch",
    )


def test_pubg_markers_with_same_first_group_but_different_second_group_remain_distinct():
    raw_text = (
        "S07336-ABCD-EFGH-JKLMN\n"
        "S07336-ABCD-PQRS-TUVWX"
    )

    assert bot.count_pubg_markers(raw_text) == 2


def test_duplicate_marker_with_one_missing_body_character_counts_once():
    raw_text = (
        "S07336-Z483-CNEE-W6C5W copy\n"
        "S07336-Z483-NEE-W6C5W copy"
    )

    assert bot.count_pubg_markers(raw_text) == 1
    assert bot.merge_pubg_expected_count(None, raw_text) == 1


def test_distinct_complete_marker_is_not_hidden_by_missing_character_rule():
    raw_text = (
        "S07336-Z483-CNEE-W6C5W\n"
        "S07336-Z483-DNEE-W6C5W"
    )

    assert bot.count_pubg_markers(raw_text) == 2


def test_run_ocr_complements_remote_when_pubg_marker_count_mismatches(monkeypatch, tmp_path):
    remote = bot.OcrResult(
        cards=("S07336-9R6P-VERQ-VTZRF", "S07336-25DY-FM6W-3K8D8"),
        raw_text=(
            "卡号：S07336-9R6P-VERQ-\n"
            "VTZRF\n"
            "卡号：S07336-25DY-\n"
            "FM6W-3K8D8\n"
            "卡号：S07336-BKBH-AAUK-\n"
            "LPJVK"
        ),
    )
    fallback = bot.OcrResult(
        cards=(
            "S07336-9R6P-VERQ-VTZRF",
            "S07336-25DY-FM6W-3K8D8",
            "S07336-BKBH-AAUK-LPJVK",
        ),
        raw_text=(
            "S07336-9R6P-VERQ-VTZRF\n"
            "S07336-25DY-FM6W-3K8D8\n"
            "S07336-BKBH-AAUK-LPJVK"
        ),
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "REMOTE_OCR_COMPLEMENT", False)
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == (
            "S07336-9R6P-VERQ-VTZRF",
            "S07336-25DY-FM6W-3K8D8",
            "S07336-BKBH-AAUK-LPJVK",
        )
        assert bot.remote_ocr_status["today_fallback_count"] == 1
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_ocrspace_resolves_single_gpu_variant_conflict_without_manual_review(
    monkeypatch, tmp_path, caplog
):
    correct = "S07336-9L9E-W6T6-FKECQ"
    remote = bot.OcrResult(
        cards=("S07336-9L9E-W6T6-FKECC",),
        raw_text="S07336-9L9E-W6T6-FKECC",
        remote_variant_conflict=True,
        remote_original_card_scores=(("S07336-9L9E-W6T6-FKECC", 0.9963),),
        remote_enhanced_card_scores=((correct, 0.9998),),
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(
        cards=(correct,),
        raw_text=f"{correct}\n{correct}",
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        with caplog.at_level("INFO", logger="telegram-card-platform"):
            result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == (correct,)
        assert result.uncertain_count == 0
        assert bot.manual_review_notifier.needs_review(result) is None
        assert "OCR VARIANT CONFLICT RESOLVED" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_gpu_variant_conflict_without_strict_cloud_support_still_needs_review(
    monkeypatch, tmp_path
):
    remote = bot.OcrResult(
        cards=("S07336-9L9E-W6T6-FKECC",),
        raw_text="S07336-9L9E-W6T6-FKECC",
        remote_variant_conflict=True,
        remote_original_card_scores=(("S07336-9L9E-W6T6-FKECC", 0.9998),),
        remote_enhanced_card_scores=(("S07336-9L9E-W6T6-FKECQ", 0.9963),),
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(
        cards=("S07336-9L9E-W6T6-FKECQ",),
        raw_text="S07336-9L9E-W6T6-FKECQ",
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        result = bot.run_ocr(write_image(tmp_path))

        assert result.uncertain_count > 0
        assert bot.manual_review_notifier.needs_review(result) is not None
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_cpu_and_ocrspace_exact_agreement_can_replace_one_high_risk_gpu_slot(
    monkeypatch, tmp_path, caplog
):
    wrong = "S07324-Z4ZH-54Y7-NBRSB"
    correct = "S07324-Z4ZH-S4Y7-NBRSB"
    remote = bot.OcrResult(
        cards=(wrong,),
        raw_text=wrong,
        remote_cpu_candidates=(correct,),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("low_card_confidence",),
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(cards=(correct,), raw_text=correct)
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        with caplog.at_level("INFO", logger="telegram-card-platform"):
            result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == (correct,)
        assert result.uncertain_count == 0
        assert bot.manual_review_notifier.needs_review(result) is None
        assert "OCR CPU+CLOUD CONFIRMED" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_dual_gpu_and_cloud_consensus_wins_before_wrong_cpu_cloud_pair(
    monkeypatch, tmp_path, caplog
):
    correct = "S07330-CE2F-BS6S-7ARJQ"
    wrong = "S07330-CE2F-BS65-7ARJQ"
    remote = bot.OcrResult(
        cards=(correct,),
        raw_text=correct,
        remote_original_card_scores=((correct, 0.9904),),
        remote_enhanced_card_scores=((correct, 0.9896),),
        remote_cpu_candidates=(wrong,),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("thin_strip_pubg",),
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(
        cards=(wrong, correct),
        raw_text=f"{wrong}\n{correct}",
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        image_path = tmp_path / "thin.jpg"
        Image.new("RGB", (700, 100), "white").save(image_path)
        with caplog.at_level("INFO", logger="telegram-card-platform"):
            result = bot.run_ocr(image_path)

        assert result.cards == (correct,)
        assert result.uncertain_count == 0
        assert result.has_unresolved_pubg_fragment is False
        assert bot.manual_review_notifier.needs_review(result) is None
        assert "OCR SOURCE CONSENSUS BEFORE CPU" in caplog.text
        assert "OCR CPU+CLOUD CONFIRMED" not in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_high_confidence_dual_gpu_result_survives_tail_only_cloud_conflicts(
    monkeypatch, tmp_path, caplog
):
    correct = "S07336-B7KS-S3NN-Q38Q8"
    cloud_wrong = (
        "S07336-B7KS-S3NN-03898",
        "S07336-B7KS-S3NN-Q38QG",
    )
    remote = bot.OcrResult(
        cards=(correct,),
        raw_text=correct,
        remote_original_card_scores=((correct, 0.9823944568634033),),
        remote_enhanced_card_scores=((correct, 0.9910047054290771),),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("thin_strip_pubg",),
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(cards=cloud_wrong, raw_text="\n".join(cloud_wrong))
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        image_path = tmp_path / "thin.jpg"
        Image.new("RGB", (700, 100), "white").save(image_path)
        with caplog.at_level("INFO", logger="telegram-card-platform"):
            result = bot.run_ocr(image_path)

        assert result.cards == (correct,)
        assert result.uncertain_count == 0
        assert result.has_unresolved_pubg_fragment is False
        assert bot.manual_review_notifier.needs_review(result) is None
        assert "OCR SOURCE CONSENSUS BEFORE CPU" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_repeated_adjacent_remote_wrap_wins_over_reordered_cloud_fragments(
    monkeypatch, tmp_path, caplog
):
    correct = "S07336-NU64-MG2H-E8MKV"
    reordered = "S07336-NU64-MKVM-G2HE8"
    remote = bot.OcrResult(
        cards=(correct,),
        raw_text=(
            "S07336-NU64-MG2H-E8\nMKV\n"
            "S07336-NU64-MG2H-E8\nMKV"
        ),
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(
        cards=(correct, reordered),
        raw_text=(
            "103000 | 5\n"
            "S07336-NU64-MG2H-E8\nMKV\nMKV\n"
            "S07336-NU64-MG2H-E8\nS07336-\nMKV\n"
            "S07336-NU64-\nMKV\nMG2H-E8\nMG2H-E8"
        ),
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        image_path = tmp_path / "wrapped-duplicate.jpg"
        Image.new("RGB", (700, 400), "white").save(image_path)
        with caplog.at_level("INFO", logger="telegram-card-platform"):
            result = bot.run_ocr(image_path)

        assert result.cards == (correct,)
        assert result.uncertain_count == 0
        assert result.has_unresolved_pubg_fragment is False
        assert bot.manual_review_notifier.needs_review(result) is None
        assert "OCR SOURCE CONSENSUS BEFORE CPU" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_cpu_candidate_alone_never_replaces_gpu_result(monkeypatch, tmp_path):
    gpu = "S07324-Z4ZH-54Y7-NBRSB"
    cpu = "S07324-Z4ZH-S4Y7-NBRSB"
    cloud_disagrees = "S07324-Z4ZH-S4Y7-NBRS8"
    remote = bot.OcrResult(
        cards=(gpu,),
        raw_text=gpu,
        remote_cpu_candidates=(cpu,),
        remote_cpu_review_required=True,
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(cards=(cloud_disagrees,), raw_text=cloud_disagrees)
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        result = bot.run_ocr(write_image(tmp_path))

        assert result.cards != (cpu,)
        assert result.uncertain_count > 0
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_exact_remote_and_cloud_card_clears_stale_wrap_uncertainty(
    monkeypatch, tmp_path, caplog
):
    card = "S07330-5MSB-F36V-AC7W4"
    remote = bot.OcrResult(
        cards=(card,),
        raw_text="S07330-5MSB-F36V-AC7\nW4",
        uncertain_count=1,
        has_unresolved_pubg_fragment=True,
    )
    cloud = bot.OcrResult(
        cards=(card,),
        raw_text="S07330-5MSB-F36V-AC7\nW4",
        uncertain_count=1,
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: cloud)

        with caplog.at_level("INFO", logger="telegram-card-platform"):
            result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == (card,)
        assert result.uncertain_count == 0
        assert result.has_unresolved_pubg_fragment is False
        assert bot.manual_review_notifier.needs_review(result) is None
        assert "OCR EXACT CROSS SOURCE CONSENSUS" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_cpu_and_cloud_resolve_duplicate_display_gpu_tail_conflict(
    monkeypatch, tmp_path
):
    gpu = "S07336-5ULK-JMZ9-EQE7F"
    confirmed = "S07336-5ULK-JMZ9-EQE7P"
    remote = bot.OcrResult(
        cards=(gpu,),
        raw_text=f"{gpu}\n{gpu}",
        remote_variant_conflict=True,
        remote_original_card_scores=((confirmed, 0.9891), (gpu, 0.9816)),
        remote_enhanced_card_scores=((gpu, 0.9998),),
        remote_cpu_candidates=(confirmed,),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("gpu_variant_conflict",),
        has_unresolved_pubg_fragment=True,
    )
    cloud = bot.OcrResult(cards=(confirmed,), raw_text=f"{confirmed}\n{confirmed}")
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: cloud)

        result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == (confirmed,)
        assert result.uncertain_count == 0
        assert bot.manual_review_notifier.needs_review(result) is None
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_partial_cloud_complement_keeps_remote_image_order(monkeypatch, tmp_path):
    remote = bot.OcrResult(
        cards=(
            "S07336-ZEBT-JFGP-KR4YE",
            "S07336-BHSN-T4TA-CH39R",
        ),
        raw_text="S07336-ZEBT-JFGP-KR4YE\nS07336-BHSN-T4TA-CH39R",
        has_unresolved_pubg_fragment=True,
    )
    fallback = bot.OcrResult(
        cards=("S07336-BHSN-T4TA-CH39R",),
        raw_text="S07336-BHSN-T4TA-CH39R",
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == remote.cards
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_multi_card_dual_gpu_consensus_ignores_one_cloud_character_conflict(
    monkeypatch, tmp_path, caplog
):
    caplog.set_level("INFO")
    cards = (
        "S07336-6LHE-R6DA-2YHHN",
        "S07336-YDCG-SCWP-WF977",
        "S07336-QEDY-ST2R-HTJDA",
        "S07336-2Z38-JYAU-3LX7L",
    )
    scores = tuple((card, 0.995) for card in cards)
    remote = bot.OcrResult(
        cards=cards,
        raw_text="\n".join(cards),
        pubg_expected_count=4,
        uncertain_count=0,
        remote_variant_conflict=True,
        remote_original_rebuilt_card_scores=scores,
        remote_enhanced_rebuilt_card_scores=scores,
        remote_cpu_candidates=(cards[0],),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("pubg_marker_count_mismatch",),
        has_unresolved_pubg_fragment=True,
    )
    fallback_cards = (
        cards[0],
        cards[2],
        "S07336-2238-JYAU-3LX7L",
    )
    fallback = bot.OcrResult(cards=fallback_cards, raw_text="\n".join(fallback_cards))
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: fallback)

        result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == cards
        assert result.uncertain_count == 0
        assert result.has_unresolved_pubg_fragment is False
        assert bot.manual_review_notifier.needs_review(result) is None
        assert "OCR MULTI CARD DUAL VARIANT CONSENSUS cards=4" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_repeated_cloud_card_completes_one_remote_slot_rejected_by_validator(
    monkeypatch, tmp_path, caplog
):
    cards = (
        "S07336-W6BB-G4EA-68FDA",
        "S07336-E8RA-VXB4-EP3Z8",
        "S07336-XJJN-T6S5-9CEJT",
    )
    confirmed = "S07336-ULVM-FXF2-TJAZL"
    rejected = "S07336-ULVM-FXF2-TJAZI"
    remote = bot.OcrResult(
        cards=cards,
        raw_text="\n".join(cards + (rejected,)),
        pubg_expected_count=4,
        uncertain_count=1,
        remote_original_rebuilt_card_scores=tuple(
            zip(cards + ("S07336-ULVM-EXF2-TJAZI",), (0.999, 0.999, 0.999, 0.922))
        ),
        remote_enhanced_rebuilt_card_scores=tuple(
            zip(cards + (rejected,), (0.999, 0.999, 0.999, 0.992))
        ),
        has_unresolved_pubg_fragment=True,
    )
    cloud = bot.OcrResult(
        cards=cards + (confirmed,),
        raw_text="\n".join(cards + (confirmed, confirmed)),
    )
    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: cloud)

        with caplog.at_level("INFO", logger="telegram-card-platform"):
            result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == cards + (confirmed,)
        assert result.uncertain_count == 0
        assert result.has_unresolved_pubg_fragment is False
        assert bot.manual_review_notifier.needs_review(result) is None
        assert "OCR CLOUD COMPLETED REJECTED REMOTE SLOT cards=4" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_complete_dual_gpu_multi_card_fast_path_skips_noisy_cloud(
    monkeypatch, tmp_path, caplog
):
    caplog.set_level("INFO")
    cards = (
        "S07330-V57R-M7VQ-3DFQX",
        "S07336-EHNP-9HPR-6YHWM",
        "S07336-U8R4-C4QL-YGWVV",
        "S07336-YGFU-VKFW-ENG2E",
    )
    original_scores = tuple(
        zip(cards, (0.9939089, 0.9904456, 0.9861397, 0.9786339))
    )
    enhanced_scores = tuple(
        zip(cards, (0.9816356, 0.9523126, 0.9951673, 0.9955719))
    )
    remote = bot.OcrResult(
        cards=cards,
        raw_text="\n".join(cards),
        pubg_expected_count=4,
        uncertain_count=0,
        remote_original_rebuilt_card_scores=original_scores,
        remote_enhanced_rebuilt_card_scores=enhanced_scores,
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("pubg_marker_without_valid_card",),
        has_unresolved_pubg_fragment=True,
    )
    cloud_called = False

    def noisy_cloud(*args, **kwargs):
        nonlocal cloud_called
        cloud_called = True
        return bot.OcrResult(
            cards=cards[:2] + cards[3:],
            raw_text="\n".join(cards[:2] + cards[3:]),
            uncertain_count=1,
        )

    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", noisy_cloud)

        result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == cards
        assert result.uncertain_count == 0
        assert result.has_unresolved_pubg_fragment is False
        assert bot.manual_review_notifier.needs_review(result) is None
        assert cloud_called is False
        assert "OCR MULTI CARD DUAL VARIANT FAST PATH cards=4" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_low_confidence_cpu_noise_does_not_force_clear_multi_card_review(
    monkeypatch, tmp_path, caplog
):
    cards = (
        "S07336-LML3-XJW3-HFEVL",
        "S07336-5QZM-PLQS-S8L3J",
        "S07336-5KC9-VU3G-E8MER",
        "S07336-TFQD-3BDS-4CDTT",
    )
    scores = ((cards[0], 0.981), (cards[1], 0.991), (cards[2], 0.994), (cards[3], 0.972))
    noisy_cpu = "S07336-5QZM-PLQ5-S813T"
    remote = bot.OcrResult(
        cards=cards,
        raw_text="\n".join(cards),
        pubg_expected_count=4,
        remote_original_rebuilt_card_scores=scores,
        remote_enhanced_rebuilt_card_scores=scores,
        remote_cpu_candidates=(noisy_cpu, cards[2], cards[3]),
        remote_cpu_candidate_scores=((noisy_cpu, 0.875), (cards[2], 0.953), (cards[3], 0.921)),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("pubg_marker_count_mismatch",),
        has_unresolved_pubg_fragment=True,
    )
    cloud_called = False

    def cloud(*args, **kwargs):
        nonlocal cloud_called
        cloud_called = True
        return bot.OcrResult(cards=())

    old_provider = bot.OCR_PROVIDER
    old_keys = bot.OCR_SPACE_API_KEYS
    try:
        bot.OCR_PROVIDER = "ocrspace"
        bot.OCR_SPACE_API_KEYS = ["key"]
        monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
        monkeypatch.setattr(bot, "run_ocrspace", cloud)

        with caplog.at_level("INFO", logger="telegram-card-platform"):
            result = bot.run_ocr(write_image(tmp_path))

        assert result.cards == cards
        assert result.uncertain_count == 0
        assert result.has_unresolved_pubg_fragment is False
        assert bot.manual_review_notifier.needs_review(result) is None
        assert cloud_called is False
        assert "OCR MULTI CARD DUAL VARIANT FAST PATH cards=4" in caplog.text
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys


def test_remote_ocr_status_command_is_registered():
    registry_source = Path("handlers/registry.py").read_text(encoding="utf-8")

    assert "remote_ocr_status_command" in registry_source
    assert 'CommandHandler("remote_ocr_status", remote_ocr_status_command)' in registry_source


def test_remote_ocr_logs_success_and_fallback(monkeypatch, tmp_path, caplog):
    payload = {
        "ok": True,
        "cards": [{"text": "S07304-WJB9-VPEZ-MUFWK", "score": 0.99}],
        "texts": [{"text": "S07304-WJB9-VPEZ-MUFWK", "score": 0.99}],
        "enhanced_used": True,
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    with caplog.at_level("INFO", logger="telegram-card-platform"):
        result = bot.run_remote_ocr(write_image(tmp_path))
        bot.record_remote_ocr_fallback("test")

    assert result is not None
    assert "REMOTE OCR START url=" in caplog.text
    assert "REMOTE OCR SUCCESS latency_ms=" in caplog.text
    assert "enhanced_used=true" in caplog.text
    assert "OCRSPACE FALLBACK reason=test" in caplog.text


def test_remote_ocr_logs_failure(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(status_code=500)))

    with caplog.at_level("INFO", logger="telegram-card-platform"):
        result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is None
    assert "REMOTE OCR FAILED reason=status 500" in caplog.text


def test_remote_ocr_health_logs_ok_and_failed(monkeypatch, caplog):
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload={"status": "ok"})))
    with caplog.at_level("INFO", logger="telegram-card-platform"):
        available, reason = bot.remote_ocr_available()

    assert available is True
    assert reason == "ok"
    assert bot.remote_ocr_status["remote_health"] is True
    assert "REMOTE OCR HEALTH OK" in caplog.text

    bot.remote_ocr_health_cache.update({"checked_at": 0.0, "result": None})
    bot.close_remote_http_client()
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(status_code=500)))
    with caplog.at_level("INFO", logger="telegram-card-platform"):
        available, reason = bot.remote_ocr_available()

    assert available is False
    assert reason == "status=500"
    assert bot.remote_ocr_status["remote_health"] is False
    assert "REMOTE OCR HEALTH FAILED reason=health status 500" in caplog.text


def test_remote_worker_health_uses_short_cache(monkeypatch):
    calls = {"count": 0}

    class CountingClient(FakeClient):
        def get(self, *args, **kwargs):
            calls["count"] += 1
            return self.response

    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: CountingClient(FakeResponse(payload={"status": "ok"})))

    first = bot.remote_worker_health()
    second = bot.remote_worker_health()

    assert first[0] is True
    assert second[0] is True
    assert calls["count"] == 1


def test_remote_ocr_status_command_outputs_requested_fields(monkeypatch):
    bot.remote_ocr_status.update(
        {
            "today_date": bot.remote_ocr_now().date().isoformat(),
            "last_success_at": "2026-06-22T10:00:00+08:00",
            "last_failed_at": "2026-06-22T10:01:00+08:00",
            "last_error": "timeout",
            "today_remote_calls": 3,
            "today_remote_success": 2,
            "today_remote_failed": 1,
            "today_fallback_count": 1,
            "today_remote_latency_total_ms": 300,
            "today_enhanced_used": 1,
            "today_cache_hits": 1,
        }
    )
    monkeypatch.setattr(bot, "remote_ocr_available", lambda: (True, "ok"))
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    replies = []

    async def reply_text(self, text):
        replies.append(text)

    message = type("Message", (), {"reply_text": reply_text})()
    user = type("User", (), {"id": 123})()
    update = type("Update", (), {"message": message, "effective_user": user})()

    asyncio.run(bot.remote_ocr_status_command(update, None))

    text = replies[0]
    assert "remote_enabled:" in text
    assert "remote_configured:" in text
    assert "remote_url:" not in text
    assert "remote_health: True" in text
    assert "last_success_at: 2026-06-22T10:00:00+08:00" in text
    assert "last_failed_at: 2026-06-22T10:01:00+08:00" in text
    assert "last_error: timeout" in text
    assert "today_remote_calls: 3" in text
    assert "today_remote_success: 2" in text
    assert "today_remote_failed: 1" in text
    assert "today_fallback_count: 1" in text
    assert "avg_remote_latency_ms: 150" in text
    assert "enhanced_rate: 33.3%" in text
    assert "cache_hit_rate: 33.3%" in text
    assert "current_provider:" in text
