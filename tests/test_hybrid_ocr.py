from pathlib import Path

import asyncio
import bot
import pytest


@pytest.fixture(autouse=True)
def reset_remote_ocr_status(monkeypatch):
    monkeypatch.setattr(bot, "REMOTE_OCR_ENABLED", True)
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
    yield
    bot.close_remote_http_client()


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
    assert result.cards == ("S07304-WJBS-VPEZ-MUFWK",)
    assert result.corrections_applied
    assert bot.remote_ocr_status["last_ok"] is True
    assert bot.remote_ocr_status["today_remote_calls"] == 1
    assert bot.remote_ocr_status["today_remote_success"] == 1
    assert bot.remote_ocr_status["today_remote_failed"] == 0
    assert bot.remote_ocr_status["today_enhanced_used"] == 1
    assert bot.remote_ocr_status["today_cache_hits"] == 1
    assert bot.avg_remote_latency_ms() >= 0


def test_remote_ocr_empty_cards_falls_back(monkeypatch, tmp_path):
    payload = {"ok": True, "cards": [], "texts": [{"text": "nothing", "score": 0.9}]}
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is None
    assert bot.remote_ocr_status["last_ok"] is False
    assert bot.remote_ocr_status["last_error"] == "empty cards"
    assert bot.remote_ocr_status["today_remote_calls"] == 1
    assert bot.remote_ocr_status["today_remote_failed"] == 1


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


def test_run_ocr_uses_remote_before_ocrspace(monkeypatch, tmp_path):
    expected = bot.OcrResult(cards=("S07304-WJB9-VPEZ-MUFWK",), raw_text="remote")
    monkeypatch.setattr(bot, "run_remote_ocr", lambda *args, **kwargs: expected)
    monkeypatch.setattr(bot, "run_ocrspace", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unused")))

    result = bot.run_ocr(write_image(tmp_path))

    assert result is expected


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


def test_remote_ocr_status_command_is_registered():
    bot_py = Path("bot.py").read_text(encoding="utf-8")

    assert "remote_ocr_status_command" in bot_py
    assert 'CommandHandler("remote_ocr_status", remote_ocr_status_command)' in bot_py


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
