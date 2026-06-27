import asyncio
from datetime import datetime
from pathlib import Path

import bot


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


class FakeBot:
    def __init__(self, status="member"):
        self.status = status

    async def get_chat_member(self, chat_id, user_id):
        return type("Member", (), {"status": self.status})()


def fake_update(user_id=123, chat_id=-100):
    message = FakeMessage()
    user = type("User", (), {"id": user_id})()
    chat = type("Chat", (), {"id": chat_id})()
    update = type("Update", (), {"message": message, "effective_user": user, "effective_chat": chat})()
    return update, message


def test_status_commands_are_registered():
    bot_py = Path("bot.py").read_text(encoding="utf-8")

    assert 'CommandHandler(["status", "ocr_status"], status_panel_command)' in bot_py
    assert r'^/状态' in bot_py


def test_status_panel_contains_requested_sections(monkeypatch, tmp_path):
    cache_path = tmp_path / "today_ocr_cache.json"
    today = datetime.now().strftime("%Y-%m-%d")
    cache_path.write_text(
        f"""
        {{
          "date": "{today}",
          "images": 2,
          "ocr_cards": [
            "S07304-WJB9-VPEZ-MUFWK",
            "PFP7-FP8X-26PH"
          ],
          "raw_candidates": [
            "S07304-WJB9-VPEZ-MUFWK",
            "S07304-WJB9-VPEZ-MUFWK"
          ]
        }}
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(bot, "TODAY_OCR_CACHE_PATH", cache_path)
    monkeypatch.setattr(bot, "LEDGER_DB_PATH", tmp_path / "ledger.sqlite3")
    bot.LEDGER_DB_PATH.write_text("", encoding="utf-8")
    monkeypatch.setattr(bot, "remote_worker_health", lambda: (True, {"status": "ok", "gpu": "RTX5070", "engine": "paddlex_ocr", "opencv": True}, "ok"))
    monkeypatch.setattr(bot, "service_active_state", lambda: "active")
    monkeypatch.setattr(bot, "git_output", lambda args: "f557b1a" if args[0] == "rev-parse" else "main")
    bot.remote_ocr_status.update(
        {
            "today_date": today,
            "today_remote_calls": 4,
            "today_remote_success": 3,
            "today_remote_failed": 1,
            "today_fallback_count": 1,
            "today_remote_latency_total_ms": 600,
            "today_enhanced_used": 2,
            "today_cache_hits": 1,
            "last_success_at": "2026-06-22T10:00:00+08:00",
            "last_failed_at": "",
            "last_error": "",
        }
    )

    text = bot.build_status_panel()

    assert "📊 机器人状态" in text
    assert "状态：运行中" in text
    assert "GPU：RTX5070" in text
    assert "引擎：paddlex_ocr" in text
    assert "当前主引擎：RTX5070" in text
    assert "缓存命中率：25.0%" in text
    assert "OpenCV增强率：50.0%" in text
    assert "图片：2 张" in text
    assert "PUBG卡密：1 个" in text
    assert "PSN卡密：1 个" in text
    assert "重复：1 个" in text


def test_status_panel_worker_offline_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "TODAY_OCR_CACHE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(bot, "remote_worker_health", lambda: (False, {}, "ConnectError"))
    monkeypatch.setattr(bot, "service_active_state", lambda: "active")

    text = bot.build_status_panel()

    assert "状态：离线" in text
    assert "备用引擎：OCR.space" in text
    assert "当前主引擎：OCR.space" in text


def test_status_panel_owner_can_query(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "build_status_panel", lambda: "status ok")
    update, message = fake_update(user_id=123)
    context = type("Context", (), {"bot": FakeBot()})()

    asyncio.run(bot.status_panel_command(update, context))

    assert message.replies == ["status ok"]


def test_status_panel_non_owner_is_denied(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    update, message = fake_update(user_id=456)
    context = type("Context", (), {"bot": FakeBot(status="member")})()

    asyncio.run(bot.status_panel_command(update, context))

    assert message.replies == ["无权限。"]


def test_status_panel_group_admin_can_query(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "build_status_panel", lambda: "admin status")
    update, message = fake_update(user_id=456)
    context = type("Context", (), {"bot": FakeBot(status="administrator")})()

    asyncio.run(bot.status_panel_command(update, context))

    assert message.replies == ["admin status"]
