import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, Message, MessageEntity, Update, User
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut
from telegram.ext import ExtBot

import handlers.message_cleanup_handler as handler
import services.group.message_cleanup as service
from handlers.registry import register_handlers
from services.background_tasks import stop_managed_background_tasks


@pytest.fixture
def no_wait(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(service.asyncio, "sleep", sleep)
    return sleep


def context_and_update(monkeypatch, *, owner=True, status="administrator", can_delete=True, chat_type="supergroup"):
    monkeypatch.setattr(handler, "is_owner_update", lambda update: owner)
    member = SimpleNamespace(status=status, can_delete_messages=can_delete)
    status_message = SimpleNamespace(edit_text=AsyncMock())
    message = SimpleNamespace(
        message_id=205, date=datetime.now(timezone.utc), sender_chat=None,
        reply_text=AsyncMock(return_value=status_message),
    )
    chat = SimpleNamespace(id=-100123, type=chat_type)
    update = SimpleNamespace(message=message, effective_chat=chat)
    bot = SimpleNamespace(id=10, get_chat_member=AsyncMock(return_value=member), delete_messages=AsyncMock())
    context = SimpleNamespace(bot=bot, bot_data={}, chat_data={}, args=[])
    return context, update, status_message


def test_scan_skips_old_missing_and_service_messages_without_stopping(no_wait):
    now = datetime.now(timezone.utc)
    dates = {i: now - timedelta(hours=49 if i < 150 else 1) for i in range(1, 256)}
    dates[150] = now - timedelta(hours=48)
    del dates[199]
    deleted = set()
    calls = []

    async def delete_messages(*, chat_id, message_ids):
        assert chat_id == -100123
        assert 1 <= len(message_ids) <= 100
        calls.append(message_ids)
        if any(i == 180 or (i in dates and now - dates[i] >= timedelta(hours=48)) for i in message_ids):
            raise BadRequest("Message can't be deleted")
        deleted.update(i for i in message_ids if i in dates)
        return True

    bot = SimpleNamespace(
        id=10, delete_messages=delete_messages,
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator", can_delete_messages=True)),
    )
    asyncio.run(service.delete_message_range(bot, -100123, "supergroup", 1, 250))
    assert deleted == set(range(151, 251)) - {180, 199}
    assert max(i for call in calls for i in call) == 250
    assert min(i for call in calls for i in call) == 1


@pytest.mark.parametrize("delay", [3, timedelta(seconds=3)])
def test_flood_wait_retries_same_batch_after_requested_delay(no_wait, delay):
    bot = SimpleNamespace(delete_messages=AsyncMock(side_effect=[RetryAfter(delay), True]))
    asyncio.run(service.delete_message_range(bot, -100123, "supergroup", 1, 3))
    assert bot.delete_messages.await_args_list[0] == bot.delete_messages.await_args_list[1]
    assert no_wait.await_args_list[0].args == (3,)


@pytest.mark.parametrize("error", [Forbidden("removed"), TimedOut(), BadRequest("Chat not found")])
def test_fatal_errors_stop_cleanup(no_wait, error):
    bot = SimpleNamespace(delete_messages=AsyncMock(side_effect=error))
    with pytest.raises(type(error)):
        asyncio.run(service.delete_message_range(bot, -100123, "supergroup", 1, 205))
    assert bot.delete_messages.await_count == 1


def test_permission_loss_is_not_treated_as_undeletable_message(no_wait):
    bot = SimpleNamespace(
        id=10, delete_messages=AsyncMock(side_effect=BadRequest("Message can't be deleted")),
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member", can_delete_messages=False)),
    )
    with pytest.raises(BadRequest, match="lost delete permission"):
        asyncio.run(service.delete_message_range(bot, -100123, "supergroup", 1, 205))
    assert bot.delete_messages.await_count == 1


@pytest.mark.parametrize("options", [
    {"owner": False}, {"status": "member"}, {"can_delete": False}, {"chat_type": "private"},
])
def test_unauthorized_requests_never_delete(monkeypatch, options):
    context, update, _ = context_and_update(monkeypatch, **options)
    asyncio.run(handler.delete_group_messages_command(update, context))
    context.bot.delete_messages.assert_not_called()
    assert not context.bot_data.get("group_message_cleanup_tasks")


@pytest.mark.parametrize("invalid", ["anonymous", "args", "old", "permission_lookup_failed"])
def test_invalid_commands_never_delete(monkeypatch, invalid):
    context, update, _ = context_and_update(monkeypatch)
    if invalid == "anonymous":
        update.message.sender_chat = update.effective_chat
    elif invalid == "args":
        context.args = ["all"]
    elif invalid == "old":
        update.message.date -= timedelta(hours=48)
    else:
        context.bot.get_chat_member.side_effect = TimedOut()
    asyncio.run(handler.delete_group_messages_command(update, context))
    context.bot.delete_messages.assert_not_called()
    assert not context.bot_data.get("group_message_cleanup_tasks")


def test_owner_command_batches_current_chat_and_remembers_completed_range(monkeypatch, no_wait):
    context, update, status = context_and_update(monkeypatch)

    async def run():
        await handler.delete_group_messages_command(update, context)
        await context.bot_data["group_message_cleanup_tasks"][update.effective_chat.id]
        assert context.chat_data["message_cleanup_completed_through"] == 205
        assert not context.bot_data["group_message_cleanup_tasks"]
        update.message.message_id = 207
        await handler.delete_group_messages_command(update, context)
        await context.bot_data["group_message_cleanup_tasks"][update.effective_chat.id]

    asyncio.run(run())
    batches = [call.kwargs["message_ids"] for call in context.bot.delete_messages.await_args_list]
    assert batches == [list(range(205, 105, -1)), list(range(105, 5, -1)), [5, 4, 3, 2, 1], [207, 206]]
    assert all(call.kwargs["chat_id"] == update.effective_chat.id for call in context.bot.delete_messages.await_args_list)
    assert "清理完成" in status.edit_text.await_args.args[0]
    assert update.message.reply_text.await_args.kwargs["do_quote"] is False


def test_failure_reports_partial_cleanup_and_allows_retry(monkeypatch, no_wait):
    context, update, status = context_and_update(monkeypatch)
    context.bot.delete_messages.side_effect = TimedOut()

    async def run():
        await handler.delete_group_messages_command(update, context)
        await context.bot_data["group_message_cleanup_tasks"][update.effective_chat.id]

    asyncio.run(run())
    assert not context.chat_data
    assert not context.bot_data["group_message_cleanup_tasks"]
    assert "清理中断" in status.edit_text.await_args.args[0]


def test_duplicate_command_does_not_start_second_task_and_shutdown_cancels(monkeypatch):
    context, update, _ = context_and_update(monkeypatch)
    started = asyncio.Event()
    wait = asyncio.Event()

    async def cleanup(*args):
        started.set()
        await wait.wait()

    monkeypatch.setattr(handler, "delete_message_range", cleanup)

    async def run():
        await handler.delete_group_messages_command(update, context)
        task = context.bot_data["group_message_cleanup_tasks"][update.effective_chat.id]
        await started.wait()
        await handler.delete_group_messages_command(update, context)
        assert context.bot_data["group_message_cleanup_tasks"][update.effective_chat.id] is task
        assert "正在清理" in update.message.reply_text.await_args.args[0]
        await stop_managed_background_tasks(SimpleNamespace(bot_data=context.bot_data))
        assert task.cancelled()
        assert not context.chat_data

    asyncio.run(run())


def test_del_registration_routes_bot_suffix_and_rejects_other_bot():
    handlers = []
    app = SimpleNamespace(add_handler=lambda item, group=0: handlers.append(item))
    register_handlers(app)
    registered = next(item for item in handlers if item.callback is handler.delete_group_messages_command)
    bot = ExtBot("123:offline-test")
    bot._bot_user = User(123, "Test", True, username="our_bot")
    for text, matches in [("/del", True), ("/del@our_bot", True), ("/del@other_bot", False)]:
        message = Message(
            1, datetime.now(timezone.utc), Chat(-100123, "supergroup"),
            from_user=User(1, "Owner", False), text=text,
            entities=[MessageEntity("bot_command", 0, len(text))],
        )
        message.set_bot(bot)
        assert (registered.check_update(Update(1, message=message)) is not None) is matches
