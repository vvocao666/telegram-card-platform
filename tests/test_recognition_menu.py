import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, Message, Update, User
from telegram.ext import ApplicationHandlerStop

from handlers import recognition_menu as menu
from handlers.registry import register_handlers
from storage.repositories.ledger_storage import LedgerStore


@pytest.fixture
def setup_menu(monkeypatch, tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    for i in range(25):
        store.remember_bot_chat(-100 - i, f"群 {i:02}", "supergroup")
        store.set_recognition_enabled(-100 - i, True)
    monkeypatch.setattr(menu.runtime, "ledger_store", store)
    monkeypatch.setattr(menu, "is_owner_update", lambda update: update.effective_user.id == 1)
    sent = SimpleNamespace(message_id=50)
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="private"), effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text="/关闭识别", reply_text=AsyncMock(return_value=sent)),
        callback_query=SimpleNamespace(message=sent, data="", answer=AsyncMock(), edit_message_text=AsyncMock()),
    )
    context = SimpleNamespace(user_data={"broadcast_selected": {-999}, "cleanup_selection": {"token": "cleanup"}})
    yield store, update, context
    store.close()


async def open_menu(update, context, command="/关闭识别"):
    update.message.text = command
    with pytest.raises(ApplicationHandlerStop):
        await menu.handle_recognition_command(update, context)


async def click(update, context, action):
    update.callback_query.data = "recognition:" + context.user_data["recognition_selection"]["token"] + ":" + action
    await menu.handle_recognition_callback(update, context)


def test_multiselect_confirmation_reopen_persistence_and_silence(setup_menu, monkeypatch):
    store, update, context = setup_menu
    store.set_class_mode_notice(-100, "on")

    async def run():
        await open_menu(update, context)
        await click(update, context, "toggle:-100")
        await click(update, context, "page:1")
        await click(update, context, "toggle:-124")
        assert context.user_data["recognition_selection"]["selected"] == {-100, -124}
        await click(update, context, "confirm")
        assert store.is_recognition_enabled(-100)
        await click(update, context, "next")
        await click(update, context, "back")
        await click(update, context, "next")
        await click(update, context, "confirm")
        assert not store.is_recognition_enabled(-100)
        assert not store.is_recognition_enabled(-124)
        assert store.is_recognition_enabled(-101)
        assert store.consume_class_mode_notice(-100) is None
        assert store.consume_class_mode_notice(-124) is None
        await menu.handle_recognition_callback(update, context)
        assert update.callback_query.answer.await_args.kwargs["show_alert"]

        # Exercise the real photo intake gate with the persisted disabled state.
        photo = SimpleNamespace(
            message=SimpleNamespace(chat_id=-100, reply_text=AsyncMock(), text=None),
            effective_chat=SimpleNamespace(id=-100, type="supergroup"), effective_user=None,
        )
        monkeypatch.setattr(menu.runtime, "remember_bot_chat", lambda update: None)
        monkeypatch.setattr(menu.runtime, "remember_ledger_user", lambda update: None)
        recognize = AsyncMock()
        monkeypatch.setattr(menu.runtime, "recognize_update", recognize)
        await menu.runtime.handle_class_mode_notice_once(photo, context)
        await menu.runtime.handle_photo(photo, context)
        photo.message.reply_text.assert_not_awaited()
        recognize.assert_not_awaited()

        reopened = LedgerStore(store.path)
        assert not reopened.is_recognition_enabled(-100)
        reopened.close()
        await open_menu(update, context, "/开启识别")
        assert {int(row["chat_id"]) for row in context.user_data["recognition_selection"]["groups"]} == {-100, -124}
        store.set_class_mode_notice(-100, "off")
        await click(update, context, "toggle:-100")
        await click(update, context, "next")
        await click(update, context, "confirm")
        assert store.is_recognition_enabled(-100)
        assert not store.is_recognition_enabled(-124)
        await menu.runtime.handle_class_mode_notice_once(photo, context)
        photo.message.reply_text.assert_not_awaited()
        await open_menu(update, context, "/开启识别")
        assert len(context.user_data["recognition_selection"]["groups"]) == 1

    asyncio.run(run())
    assert context.user_data["broadcast_selected"] == {-999}
    assert context.user_data["cleanup_selection"] == {"token": "cleanup"}


@pytest.mark.parametrize("invalid", ["owner", "group", "old_token", "wrong_message", "unknown_group", "cancel"])
def test_invalid_or_cancelled_menu_does_not_change_state(setup_menu, invalid):
    store, update, context = setup_menu

    async def run():
        await open_menu(update, context)
        await click(update, context, "toggle:-100")
        await click(update, context, "next")
        if invalid == "owner":
            update.effective_user.id = 2
        elif invalid == "group":
            update.effective_chat.type = "supergroup"
        elif invalid == "wrong_message":
            update.callback_query.message = SimpleNamespace(message_id=49)
        elif invalid == "old_token":
            token = context.user_data["recognition_selection"]["token"]
            await open_menu(update, context)
            update.callback_query.data = f"recognition:{token}:confirm"
            await menu.handle_recognition_callback(update, context)
            return
        elif invalid == "unknown_group":
            await click(update, context, "back")
            await click(update, context, "toggle:-999")
            assert -999 not in context.user_data["recognition_selection"]["selected"]
            return
        elif invalid == "cancel":
            await click(update, context, "cancel")
            await menu.handle_recognition_callback(update, context)
            return
        await click(update, context, "confirm")

    asyncio.run(run())
    assert all(store.is_recognition_enabled(-100 - i) for i in range(25))


def test_empty_open_list_and_unauthorized_command(setup_menu):
    store, update, context = setup_menu

    async def run():
        await open_menu(update, context)
        await open_menu(update, context, "/开启识别")
        assert "recognition_selection" not in context.user_data
        assert "没有已关闭" in update.message.reply_text.await_args.args[0]
        update.effective_user.id = 2
        await open_menu(update, context)
        assert "只有机器人主人" in update.message.reply_text.await_args.args[0]

    asyncio.run(run())
    assert store.is_recognition_enabled(-100)


def test_chinese_commands_route_before_broadcast_text_and_only_in_private():
    handlers = []
    register_handlers(SimpleNamespace(add_handler=lambda handler, group=0: handlers.append((group, handler))))
    group, handler = next((g, h) for g, h in handlers if h.callback is menu.handle_recognition_command)
    assert group == -2
    for text, chat_type, expected in [
        ("/关闭识别", "private", True), ("/开启识别", "private", True),
        ("/关闭识别@our_bot", "private", True), ("/关闭识别", "supergroup", False),
        ("关闭识别", "private", False), ("/开启识别全部", "private", False),
    ]:
        message = Message(1, datetime.now(timezone.utc), Chat(1, chat_type), from_user=User(1, "Owner", False), text=text)
        assert bool(handler.check_update(Update(1, message=message))) is expected
