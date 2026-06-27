import asyncio
import json
import time
from pathlib import Path

import pytest
from telegram.ext import ApplicationHandlerStop

from handlers.support_relay_handler import handle_support_relay
from services.support_relay import (
    RelayTarget,
    find_relay_target,
    remember_relay_message,
    relay_incoming_private_message,
    relay_owner_reply,
)


class FakeUser:
    def __init__(self, user_id: int, username: str = "user") -> None:
        self.id = user_id
        self.username = username
        self.first_name = "Test"
        self.last_name = ""


class FakeChat:
    def __init__(self, chat_id: int, chat_type: str = "private") -> None:
        self.id = chat_id
        self.type = chat_type


class FakeMessage:
    def __init__(self, text: str, chat_id: int, message_id: int, user_id: int, reply_to_message=None) -> None:
        self.text = text
        self.caption = None
        self.chat_id = chat_id
        self.message_id = message_id
        self.from_user = FakeUser(user_id)
        self.reply_to_message = reply_to_message
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, message: FakeMessage, chat_type: str = "private") -> None:
        self.message = message
        self.effective_user = message.from_user
        self.effective_chat = FakeChat(message.chat_id, chat_type)


class FakeBot:
    def __init__(self) -> None:
        self.next_message_id = 100
        self.sent_messages: list[dict] = []
        self.copied_messages: list[dict] = []

    async def send_message(self, **kwargs):
        self.next_message_id += 1
        self.sent_messages.append(kwargs)
        return type("Sent", (), {"message_id": self.next_message_id})()

    async def copy_message(self, **kwargs):
        self.next_message_id += 1
        self.copied_messages.append(kwargs)
        return type("Copied", (), {"message_id": self.next_message_id})()


class FakeContext:
    def __init__(self) -> None:
        self.bot = FakeBot()


def test_relay_mapping_is_persisted(tmp_path):
    path = tmp_path / "relay.json"
    remember_relay_message(101, RelayTarget(chat_id=200, user_id=200, source_message_id=3, created_at=time.time()), path)

    assert find_relay_target(101, path).chat_id == 200
    assert json.loads(path.read_text(encoding="utf-8"))["101"]["source_message_id"] == 3


def test_non_owner_private_message_is_forwarded_to_owner(tmp_path):
    update = FakeUpdate(FakeMessage("你好", chat_id=200, message_id=7, user_id=200))
    context = FakeContext()

    handled = asyncio.run(relay_incoming_private_message(update, context, "100", tmp_path / "relay.json"))

    assert handled is True
    assert context.bot.sent_messages[0]["chat_id"] == 100
    assert context.bot.copied_messages[0]["from_chat_id"] == 200
    assert update.message.replies == ["已收到，消息已转给管理员。"]


def test_owner_reply_is_sent_back_to_original_user(tmp_path):
    path = tmp_path / "relay.json"
    remember_relay_message(101, RelayTarget(chat_id=200, user_id=200, source_message_id=7, created_at=time.time()), path)
    replied = FakeMessage("原消息", chat_id=100, message_id=101, user_id=100)
    owner_reply = FakeMessage("我回复你", chat_id=100, message_id=102, user_id=100, reply_to_message=replied)
    update = FakeUpdate(owner_reply)
    context = FakeContext()

    handled = asyncio.run(relay_owner_reply(update, context, "100", path))

    assert handled is True
    assert context.bot.copied_messages[0]["chat_id"] == 200
    assert context.bot.copied_messages[0]["from_chat_id"] == 100
    assert owner_reply.replies == ["已发送给用户。"]


def test_owner_non_reply_is_not_consumed(tmp_path):
    update = FakeUpdate(FakeMessage("普通私聊", chat_id=100, message_id=1, user_id=100))
    context = FakeContext()

    handled = asyncio.run(relay_owner_reply(update, context, "100", tmp_path / "relay.json"))

    assert handled is False
    assert context.bot.sent_messages == []


def test_handler_stops_after_relay(monkeypatch, tmp_path):
    monkeypatch.setattr("services.support_relay.RELAY_MAP_PATH", tmp_path / "relay.json")
    monkeypatch.setattr("services.runtime.OWNER_CHAT_ID", "100")
    update = FakeUpdate(FakeMessage("联系管理员", chat_id=200, message_id=7, user_id=200))

    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(handle_support_relay(update, FakeContext()))


def test_bot_registers_support_relay_before_photo_and_ledger():
    bot_py = Path("bot.py").read_text(encoding="utf-8")

    assert "handle_support_relay" in bot_py
    assert "group=-2" in bot_py
    relay_registration = "handle_support_relay), group=-2"
    ledger_registration = "handle_priority_ledger_text), group=-1"
    assert bot_py.index(relay_registration) < bot_py.index(ledger_registration)
