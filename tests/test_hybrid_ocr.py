from pathlib import Path

import asyncio
import bot
import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def reset_remote_ocr_status(monkeypatch):
    old_remote_url = bot.REMOTE_OCR_URL
    monkeypatch.setattr(bot, "REMOTE_OCR_ENABLED", True)
    monkeypatch.setattr(bot, "REMOTE_OCR_URL", "http://100.81.208.104:8000")
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


def test_run_ocr_verifies_thin_strip_remote_conflict_with_ocrspace(monkeypatch, tmp_path):
    image_path = tmp_path / "thin.jpg"
    Image.new("RGB", (500, 80), "white").save(image_path)
    remote = bot.OcrResult(cards=("S07324-N4RB-3744-V3Y8N",), raw_text="remote")
    cloud = bot.OcrResult(cards=("S07324-N4RB-3744-V3Y8M",), raw_text="cloud")
    monkeypatch.setattr(bot, "OCR_PROVIDER", "ocrspace")
    monkeypatch.setattr(bot, "OCR_SPACE_API_KEYS", ["key"])
    monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: remote)
    monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: cloud)

    result = bot.run_ocr(image_path)

    assert result.cards == cloud.cards
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
    assert "remote_url:" in text
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
