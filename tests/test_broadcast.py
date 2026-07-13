from pathlib import Path

import asyncio

import bot
import pytest
from services.broadcast import broadcast_service


@pytest.fixture(autouse=True)
def clear_notify_cooldowns():
    bot.notify_all_cooldowns.clear()
    yield
    bot.notify_all_cooldowns.clear()


class FakeRow(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


class FakeLedgerStore:
    def __init__(self):
        self.groups = [
            FakeRow(chat_id=-1001, title="群A", chat_type="supergroup", updated_at="2026-06-24"),
            FakeRow(chat_id=-1002, title="群B", chat_type="supergroup", updated_at="2026-06-24"),
        ]
        self.members_by_chat = {
            -1001: [
                FakeRow(user_id=1, username="user1", display_name="User One", is_bot=0, updated_at="2026-06-24"),
                FakeRow(user_id=2, username="", display_name="No Username", is_bot=0, updated_at="2026-06-24"),
            ],
            -1002: [
                FakeRow(user_id=3, username="other_group", display_name="Other", is_bot=0, updated_at="2026-06-24"),
            ],
        }
        self.operator_ids = {123}

    def list_active_bot_groups(self):
        return self.groups

    def remember_bot_chat(self, *args, **kwargs):
        return None

    def remember_user(self, *args, **kwargs):
        return None

    def is_operator(self, chat_id, user_id, owner_ids):
        return user_id in owner_ids or user_id in self.operator_ids

    def list_active_known_members(self, chat_id, days=30):
        return list(self.members_by_chat.get(chat_id, []))

    def count_active_known_members(self, chat_id, days=None):
        return len(self.members_by_chat.get(chat_id, []))

    def get_chat_owner_id(self, chat_id):
        return None


class LargeMemberStore(FakeLedgerStore):
    def __init__(self, total):
        super().__init__()
        self.members_by_chat[-1001] = [
            FakeRow(user_id=1000 + index, username=f"user{index}", display_name=f"User {index}", is_bot=0, updated_at="2026-06-24")
            for index in range(total)
        ]


class FakeMessage:
    def __init__(self, text, chat_id=123, chat_type="private"):
        self.text = text
        self.chat_id = chat_id
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeCallbackQuery:
    def __init__(self, data, user_id=123):
        self.data = data
        self.from_user = type("User", (), {"id": user_id})()
        self.edits = []
        self.markups = []

    async def answer(self):
        return None

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))

    async def edit_message_reply_markup(self, **kwargs):
        self.markups.append(kwargs)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()
        self.user_data = {}


def fake_update(text, user_id=123, chat_id=123, chat_type="private"):
    user = type("User", (), {"id": user_id, "username": "owner", "first_name": "Owner", "last_name": "", "is_bot": False})()
    chat = type("Chat", (), {"id": chat_id, "type": chat_type, "title": "Test Group"})()
    message = FakeMessage(text, chat_id=chat_id, chat_type=chat_type)
    return type("Update", (), {"message": message, "effective_user": user, "effective_chat": chat})()


def fake_callback_update(data, user_id=123):
    user = type("User", (), {"id": user_id})()
    query = FakeCallbackQuery(data, user_id=user_id)
    return type("Update", (), {"callback_query": query, "effective_user": user, "effective_chat": None})()


def test_broadcast_service_exports_flow_functions():
    snapshot = Path("services/broadcast/broadcast_service.py")

    assert snapshot.exists()
    assert broadcast_service.broadcast_group_keyboard is bot.broadcast_group_keyboard
    assert broadcast_service.start_broadcast is bot.start_broadcast
    assert broadcast_service.handle_broadcast_callback is bot.handle_broadcast_callback
    assert broadcast_service.handle_broadcast_text is bot.handle_broadcast_text


def test_private_broadcast_returns_group_selection(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())
    update = fake_update("/broadcast")
    context = FakeContext()

    asyncio.run(bot.start_broadcast(update, context))

    assert "请选择要广播的群" in update.message.replies[0][0]
    assert update.message.replies[0][1]["reply_markup"].inline_keyboard


def test_broadcast_group_keyboard_uses_checkmark(monkeypatch):
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())

    keyboard = bot.broadcast_group_keyboard({-1001})
    labels = [row[0].text for row in keyboard.inline_keyboard[:2]]

    assert labels[0].startswith("√ ")
    assert labels[1].startswith("□ ")


def test_group_broadcast_does_not_start(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())
    update = fake_update("/broadcast", chat_id=-1001, chat_type="supergroup")
    context = FakeContext()

    asyncio.run(bot.start_broadcast(update, context))

    assert update.message.replies == []
    assert context.user_data == {}


def test_broadcast_text_previews_then_confirm_sends_to_selected_groups(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())
    context = FakeContext()
    context.user_data["broadcast_selected"] = {-1001, -1002}
    context.user_data["broadcast_waiting_text"] = True
    update = fake_update("今晚维护10分钟 ✅")

    handled = asyncio.run(bot.handle_broadcast_text(update, context))

    assert handled is True
    assert "广播目标" in update.message.replies[0][0]
    assert "群A" in update.message.replies[0][0]
    assert "确认发送" in update.message.replies[0][1]["reply_markup"].inline_keyboard[0][0].text

    callback_update = fake_callback_update("broadcast:confirm")
    asyncio.run(bot.handle_broadcast_callback(callback_update, context))

    assert context.bot.sent == [(-1002, "今晚维护10分钟 ✅", {}), (-1001, "今晚维护10分钟 ✅", {})]
    assert "广播完成" in callback_update.callback_query.edits[0][0]


def test_group_notify_all_mentions_current_group_members(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())
    monkeypatch.setattr(bot.asyncio, "sleep", lambda delay: asyncio.sleep(0))
    update = fake_update("通知所有人 今晚维护10分钟", chat_id=-1001, chat_type="supergroup")
    context = FakeContext()

    asyncio.run(bot.notify_all_command(update, context))

    assert update.message.replies == []
    assert context.bot.sent[0][0] == -1001
    reply = context.bot.sent[0][1]
    assert "📢 通知所有人" in reply
    assert "今晚维护10分钟" in reply
    assert "@user1" in reply
    assert 'tg://user?id=2' in reply
    assert "other_group" not in reply


def test_private_notify_all_does_not_trigger(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    update = fake_update("通知所有人 今晚维护")
    context = FakeContext()

    asyncio.run(bot.notify_all_command(update, context))

    assert update.message.replies == []


def test_notify_all_rejects_normal_user(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())
    update = fake_update("通知所有人", user_id=456, chat_id=-1001, chat_type="supergroup")
    context = FakeContext()

    asyncio.run(bot.notify_all_command(update, context))

    assert update.message.replies[0][0] == "无权限。"


def test_notify_all_splits_more_than_50_members(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", LargeMemberStore(51))

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(bot.asyncio, "sleep", no_sleep)
    update = fake_update("通知所有人", chat_id=-1001, chat_type="supergroup")
    context = FakeContext()

    asyncio.run(bot.notify_all_command(update, context))

    assert update.message.replies == []
    assert len(context.bot.sent) == 2
    assert context.bot.sent[0][1].count("@user") == 50
    assert context.bot.sent[1][1].count("@user") == 1


def test_notify_members_shows_cached_counts(monkeypatch):
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "123")
    monkeypatch.setattr(bot, "ledger_store", FakeLedgerStore())
    update = fake_update("/notify_members", chat_id=-1001, chat_type="supergroup")
    context = FakeContext()

    asyncio.run(bot.notify_members_command(update, context))

    text = update.message.replies[0][0]
    assert "缓存人数：2" in text
    assert "最近7天活跃：2" in text
    assert "最近30天活跃：2" in text


def test_broadcast_and_notify_commands_are_registered():
    registry_source = Path("handlers/registry.py").read_text(encoding="utf-8")

    assert 'CommandHandler("broadcast", start_broadcast)' in registry_source
    assert 'CommandHandler(["notify_all", "at_all"], notify_all_command)' in registry_source
    assert 'CommandHandler("notify_members", notify_members_command)' in registry_source
