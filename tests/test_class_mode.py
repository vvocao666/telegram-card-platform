import asyncio
from pathlib import Path

import pytest

import bot
from storage.repositories.ledger_storage import LedgerStore


class FakeUser:
    def __init__(self, user_id: int = 1, is_bot: bool = False) -> None:
        self.id = user_id
        self.username = "tester"
        self.first_name = "Test"
        self.last_name = ""
        self.is_bot = is_bot


class FakeChat:
    def __init__(self, chat_id: int = -1001, chat_type: str = "group") -> None:
        self.id = chat_id
        self.type = chat_type
        self.title = "group"


class FakeMessage:
    def __init__(self, text: str | None, chat_id: int = -1001, user_id: int = 1) -> None:
        self.text = text
        self.caption = None
        self.chat_id = chat_id
        self.message_id = 10
        self.reply_to_message = None
        self.from_user = FakeUser(user_id)
        self.new_chat_members = None
        self.left_chat_member = None
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, text: str | None, user_id: int = 1, chat_id: int = -1001, chat_type: str = "group") -> None:
        self.message = FakeMessage(text, chat_id=chat_id, user_id=user_id)
        self.effective_user = self.message.from_user
        self.effective_chat = FakeChat(chat_id, chat_type=chat_type)


class FakeContext:
    args: list[str] = []


@pytest.fixture()
def temp_store(monkeypatch, tmp_path: Path):
    old_store = bot.ledger_store
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(bot, "ledger_store", store)
    yield store
    monkeypatch.setattr(bot, "ledger_store", old_store)
    store.close()


def test_class_on_enables_recognition_and_replies_once(temp_store):
    chat_id = -1001
    temp_store.set_chat_owner(chat_id, 1, replace=True)
    temp_store.set_recognition_enabled(chat_id, False)

    with pytest.raises(bot.ApplicationHandlerStop):
        asyncio.run(bot.handle_class_mode_command(FakeUpdate("/上课"), FakeContext()))

    assert temp_store.is_recognition_enabled(chat_id) is True
    first = FakeUpdate("hello")
    second = FakeUpdate("hello again")
    asyncio.run(bot.handle_class_mode_notice_once(first, FakeContext()))
    asyncio.run(bot.handle_class_mode_notice_once(second, FakeContext()))

    assert first.message.replies == ["✅本群已上课，开始接收卡密。"]
    assert second.message.replies == []


def test_class_off_disables_recognition_and_replies_once(temp_store):
    chat_id = -1001
    temp_store.set_chat_owner(chat_id, 1, replace=True)
    temp_store.set_recognition_enabled(chat_id, True)

    with pytest.raises(bot.ApplicationHandlerStop):
        asyncio.run(bot.handle_class_mode_command(FakeUpdate("/下课"), FakeContext()))

    assert temp_store.is_recognition_enabled(chat_id) is False
    first = FakeUpdate("hello")
    second = FakeUpdate("hello again")
    asyncio.run(bot.handle_class_mode_notice_once(first, FakeContext()))
    asyncio.run(bot.handle_class_mode_notice_once(second, FakeContext()))

    assert first.message.replies == [
        "❌本群已下课，已经停止接收卡密；\n\n请您【勿发卡密以及撤回卡密】，如卡密丢失概不负责，谢谢。"
    ]
    assert second.message.replies == []


def test_class_mode_command_requires_group_owner(temp_store):
    chat_id = -1001
    temp_store.set_chat_owner(chat_id, 1, replace=True)
    update = FakeUpdate("/下课", user_id=2)

    with pytest.raises(bot.ApplicationHandlerStop):
        asyncio.run(bot.handle_class_mode_command(update, FakeContext()))

    assert update.message.replies == ["只有本群管理权限用户可以使用上课/下课。"]
    assert temp_store.is_recognition_enabled(chat_id) is True


def test_class_mode_notice_does_not_trigger_in_private(temp_store):
    chat_id = 1001
    temp_store.set_class_mode_notice(chat_id, "on")
    update = FakeUpdate("hello", chat_id=chat_id, chat_type="private")

    asyncio.run(bot.handle_class_mode_notice_once(update, FakeContext()))

    assert update.message.replies == []
