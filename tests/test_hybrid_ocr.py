from pathlib import Path

import bot


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
    }
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is not None
    assert result.cards == ("S07304-WJB9-VPEZ-MUFWK",)
    assert bot.remote_ocr_status["last_ok"] is True


def test_remote_ocr_empty_cards_falls_back(monkeypatch, tmp_path):
    payload = {"ok": True, "cards": [], "texts": [{"text": "nothing", "score": 0.9}]}
    monkeypatch.setattr(bot.httpx, "Client", lambda timeout: FakeClient(FakeResponse(payload=payload)))

    result = bot.run_remote_ocr(write_image(tmp_path))

    assert result is None
    assert bot.remote_ocr_status["last_ok"] is False
    assert bot.remote_ocr_status["last_error"] == "empty cards"


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
    finally:
        bot.OCR_PROVIDER = old_provider
        bot.OCR_SPACE_API_KEYS = old_keys
        bot.VERIFY_WITH_LOCAL = old_verify
        bot.LOCAL_COMPLEMENT = old_complement


def test_remote_ocr_status_command_is_registered():
    bot_py = Path("bot.py").read_text(encoding="utf-8")

    assert "remote_ocr_status_command" in bot_py
    assert 'CommandHandler("remote_ocr_status", remote_ocr_status_command)' in bot_py
