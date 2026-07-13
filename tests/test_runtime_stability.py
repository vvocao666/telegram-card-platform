from pathlib import Path

import bot
import httpx


class TimeoutClient:
    created = 0

    def __init__(self, *args, **kwargs):
        type(self).created += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    def close(self):
        pass


def test_ocrspace_timeout_returns_empty_result_without_secondary_exception(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(bot, "OCR_SPACE_API_KEYS", ["test-key"])
    monkeypatch.setattr(bot, "OCR_SPACE_ENGINES", [2])
    monkeypatch.setattr(bot, "ocrspace_cooldown_until", 0.0)
    monkeypatch.setattr(bot, "prepare_ocrspace_image", lambda path: path)
    monkeypatch.setattr(bot.httpx, "Client", TimeoutClient)

    bot.close_ocrspace_http_client()
    try:
        result = bot.run_ocrspace(image_path)
    finally:
        bot.close_ocrspace_http_client()

    assert result.cards == ()
    assert result.psn_cards == ()


def test_ocrspace_reuses_http_client_between_images(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(bot, "OCR_SPACE_API_KEYS", ["test-key"])
    monkeypatch.setattr(bot, "OCR_SPACE_ENGINES", [2])
    monkeypatch.setattr(bot, "ocrspace_cooldown_until", 0.0)
    monkeypatch.setattr(bot, "prepare_ocrspace_image", lambda path: path)
    monkeypatch.setattr(bot.httpx, "Client", TimeoutClient)
    TimeoutClient.created = 0

    bot.close_ocrspace_http_client()
    try:
        bot.run_ocrspace(image_path)
        bot.run_ocrspace(image_path)
    finally:
        bot.close_ocrspace_http_client()

    assert TimeoutClient.created == 1


def test_production_entrypoint_registers_existing_membership_and_cutoff_handlers():
    source = Path("handlers/registry.py").read_text(encoding="utf-8")

    assert "ChatMemberHandler(handle_bot_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)" in source
    assert "filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_chat_member" in source
    assert '"set_cutoff"' in source
    assert '"cutoff"' in source
