from pathlib import Path

import bot
import httpx


class TimeoutClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        raise httpx.ReadTimeout("timed out")


def test_ocrspace_timeout_returns_empty_result_without_secondary_exception(monkeypatch, tmp_path):
    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(bot, "OCR_SPACE_API_KEYS", ["test-key"])
    monkeypatch.setattr(bot, "OCR_SPACE_ENGINES", [2])
    monkeypatch.setattr(bot, "ocrspace_cooldown_until", 0.0)
    monkeypatch.setattr(bot, "prepare_ocrspace_image", lambda path: path)
    monkeypatch.setattr(bot.httpx, "Client", TimeoutClient)

    result = bot.run_ocrspace(image_path)

    assert result.cards == ()
    assert result.psn_cards == ()


def test_production_entrypoint_registers_existing_membership_and_cutoff_handlers():
    source = Path("bot.py").read_text(encoding="utf-8")

    assert "ChatMemberHandler(handle_bot_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)" in source
    assert '"set_cutoff"' in source
    assert '"cutoff"' in source
