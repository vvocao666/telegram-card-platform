from __future__ import annotations

from pathlib import Path

import bot
from services.ocr.ocrspace_provider import recognize_ocrspace


CARD = "S07362-QZZ3-GBT8-K2JWP"


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError("transient 5xx must be handled before raise_for_status")

    def json(self) -> dict:
        return self._payload


class SequentialClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.engines: list[str] = []

    def post(self, _url, *, data, **_kwargs):
        self.engines.append(str(data["OCREngine"]))
        return self.responses.pop(0)


def test_ocrspace_continues_to_next_engine_after_transient_5xx(monkeypatch, tmp_path: Path, caplog):
    image = tmp_path / "card.png"
    image.write_bytes(b"test image")
    client = SequentialClient(
        [
            FakeResponse(503),
            FakeResponse(
                200,
                {
                    "IsErroredOnProcessing": False,
                    "ParsedResults": [{"ParsedText": CARD}],
                },
            ),
        ]
    )
    monkeypatch.setattr(bot, "OCR_SPACE_API_KEYS", ["test-key"])
    monkeypatch.setattr(bot, "OCR_SPACE_ENGINES", ["1", "2"])
    monkeypatch.setattr(bot, "OCR_SPACE_TOTAL_TIMEOUT", 30.0)
    monkeypatch.setattr(bot, "prepare_ocrspace_image", lambda _path: image)
    monkeypatch.setattr(bot, "get_ocrspace_http_client", lambda _timeout: client)
    monkeypatch.setattr(bot, "remote_ocr_is_circuit_open", lambda: False)

    result = recognize_ocrspace(bot, image)

    assert result.cards == (CARD,)
    assert client.engines == ["1", "2"]
    assert "OCRSPACE TRANSIENT FAILURE engine=1" in caplog.text
