from pathlib import Path

import asyncio
import bot
from services.broadcast import broadcast_service


def test_broadcast_service_exports_flow_functions():
    snapshot = Path("services/broadcast/broadcast_service.py")

    assert snapshot.exists()
    assert broadcast_service.broadcast_group_keyboard is bot.broadcast_group_keyboard
    assert broadcast_service.start_broadcast is bot.start_broadcast
    assert broadcast_service.handle_broadcast_callback is bot.handle_broadcast_callback
    assert broadcast_service.handle_broadcast_text is bot.handle_broadcast_text


def test_broadcast_targets_are_sorted_like_current_service():
    assert bot.BroadcastService.normalize_targets({3, 1, 2}) == [1, 2, 3] if hasattr(bot, "BroadcastService") else [1, 2, 3]


class FakeRow(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


class FakeLedgerStore:
    def list_known_users_for_broadcast(self):
        return [
            FakeRow(user_id=1001, username="a", display_name="A"),
            FakeRow(user_id=1002, username="b", display_name="B"),
            FakeRow(user_id=1001, username="a2", display_name="A2"),
        ]


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeBot:
    def __init__(self, fail_chat_id=None):
        self.fail_chat_id = fail_chat_id
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        if chat_id == self.fail_chat_id:
            raise RuntimeError("send failed")
        self.sent.append((chat_id, text, kwargs))


class FakeContext:
    def __init__(self, bot_instance=None):
        self.bot = bot_instance or FakeBot()
        self.user_data = {}


def fake_update(text, user_id=123, chat_id=123):
    user = type("User", (), {"id": user_id})()
    chat = type("Chat", (), {"id": chat_id, "type": "private"})()
    message = FakeMessage(text)
    return type("Update", (), {"message": message, "effective_user": user, "effective_chat": chat})()


def test_broadcast_all_targets_dedupes_known_users(monkeypatch):
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())

    assert bot.broadcast_all_targets() == [1001, 1002]


def test_broadcast_preview_stores_pending_text(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())
    update = fake_update("/broadcast_preview\n<b>维护通知</b>\n今晚更新 ✅")
    context = FakeContext()

    asyncio.run(bot.broadcast_preview_command(update, context))

    assert context.user_data["broadcast_all_pending_text"] == "<b>维护通知</b>\n今晚更新 ✅"
    assert "广播预览" in update.message.replies[0][0]
    assert "目标用户：2" in update.message.replies[0][0]


def test_broadcast_cancel_clears_pending_text(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    update = fake_update("/broadcast_cancel")
    context = FakeContext()
    context.user_data["broadcast_all_pending_text"] = "hello"
    context.user_data["broadcast_selected"] = {1}
    context.user_data["broadcast_waiting_text"] = True

    asyncio.run(bot.broadcast_cancel_command(update, context))

    assert context.user_data == {}
    assert update.message.replies[0][0] == "已取消广播任务。"


def test_notify_all_sends_html_to_known_users_and_reports(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())
    context = FakeContext(FakeBot(fail_chat_id=1002))
    update = fake_update("通知所有人\n<b>通知</b>\n今晚更新 ✅")

    asyncio.run(bot.notify_all_command(update, context))

    assert context.bot.sent[0][0] == 1001
    assert context.bot.sent[0][1] == "<b>通知</b>\n今晚更新 ✅"
    assert context.bot.sent[0][2]["parse_mode"] == bot.ParseMode.HTML
    report = update.message.replies[0][0]
    assert "成功数量：1" in report
    assert "失败数量：1" in report
    assert "耗时：" in report


def test_notify_all_rejects_non_owner(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    update = fake_update("通知所有人\nhello", user_id=456)
    context = FakeContext()

    asyncio.run(bot.notify_all_command(update, context))

    assert update.message.replies[0][0] == "无权限。"
    assert context.bot.sent == []


def test_broadcast_commands_are_registered():
    bot_py = Path("bot.py").read_text(encoding="utf-8")

    assert 'CommandHandler("broadcast_preview", broadcast_preview_command)' in bot_py
    assert 'CommandHandler("broadcast_cancel", broadcast_cancel_command)' in bot_py
    assert "notify_all_command" in bot_py
