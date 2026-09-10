import asyncio
import json
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import Forbidden, RetryAfter, TimedOut
from telegram.request import HTTPXRequest

import handlers.message_cleanup_menu as menu
import handlers.message_cleanup_handler as handler
from config.application import build_telegram_application
from services.background_tasks import stop_managed_background_tasks
from services.group.message_positions import GroupMessagePositions, PositionTrackingRequest


def setup_menu(monkeypatch, tmp_path, count=3):
    groups = [{"chat_id": -100 - i, "title": f"群 {i}", "chat_type": "supergroup"} for i in range(count)]
    monkeypatch.setattr(menu, "is_owner_update", lambda update: True)
    monkeypatch.setattr(menu.runtime, "ledger_store", SimpleNamespace(list_active_bot_groups=lambda: groups))
    bot = SimpleNamespace(
        id=10,
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator", can_delete_messages=True)),
        delete_messages=AsyncMock(), send_message=AsyncMock(),
    )
    positions = GroupMessagePositions(tmp_path / "positions.sqlite3")
    positions.record_result([{"chat": {"id": g["chat_id"], "type": "supergroup"}, "message_id": 5} for g in groups])
    context = SimpleNamespace(
        bot=bot, bot_data={"group_message_positions": positions}, user_data={}, args=[],
        application=SimpleNamespace(chat_data=defaultdict(dict)),
    )
    sent = SimpleNamespace(message_id=50, edit_text=AsyncMock())
    message = SimpleNamespace(reply_text=AsyncMock(return_value=sent))
    query = SimpleNamespace(message=sent, data="", answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(type="private"), callback_query=query)
    return context, update, groups


async def click(update, context, action):
    update.callback_query.data = "cleanup:" + context.user_data["cleanup_selection"]["token"] + ":" + action
    await menu.handle_cleanup_callback(update, context)


def test_menu_only_lists_groups_with_verified_delete_permission(monkeypatch, tmp_path):
    context, update, groups = setup_menu(monkeypatch, tmp_path, count=6)
    groups[-1]["chat_type"] = "group"
    context.bot.get_chat_member.side_effect = [
        SimpleNamespace(status="administrator", can_delete_messages=True),
        SimpleNamespace(status="member", can_delete_messages=False),
        SimpleNamespace(status="administrator", can_delete_messages=False),
        Forbidden("bot was kicked"),
        TimedOut(),
        SimpleNamespace(status="administrator", can_delete_messages=False),
    ]

    asyncio.run(menu.start_cleanup_menu(update, context))

    state = context.user_data["cleanup_selection"]
    assert state["groups"] == [groups[0], groups[5]]
    labels = [r[0].text for r in menu.selection_keyboard(state).inline_keyboard[:-1]]
    assert labels == ["□ 群 0", "□ 群 5"]
    assert context.bot.get_chat_member.await_count == 6
    context.bot.delete_messages.assert_not_awaited()


def test_menu_without_eligible_groups_invalidates_previous_selection(monkeypatch, tmp_path):
    context, update, _ = setup_menu(monkeypatch, tmp_path)
    context.user_data["cleanup_selection"] = {"token": "old", "selected": {-100}}
    context.bot.get_chat_member.return_value = SimpleNamespace(status="member", can_delete_messages=False)

    asyncio.run(menu.start_cleanup_menu(update, context))

    assert "cleanup_selection" not in context.user_data
    assert "目前没有可显示的群" in update.callback_query.message.edit_text.await_args.args[0]
    assert "reply_markup" not in update.callback_query.message.edit_text.await_args.kwargs
    context.bot.delete_messages.assert_not_awaited()


def test_menu_rechecks_permission_before_deleting(monkeypatch, tmp_path):
    context, update, _ = setup_menu(monkeypatch, tmp_path)

    async def run():
        await menu.start_cleanup_menu(update, context)
        await click(update, context, "toggle:-100")
        await click(update, context, "next")
        context.bot.get_chat_member.return_value = SimpleNamespace(status="administrator", can_delete_messages=False)
        await click(update, context, "confirm")
        await asyncio.gather(*context.bot_data["private_message_cleanup_tasks"].values())

    asyncio.run(run())
    context.bot.delete_messages.assert_not_awaited()
    assert "完成 0 个群" in update.callback_query.edit_message_text.await_args.args[0]


def test_menu_acknowledges_before_bounded_parallel_permission_checks(monkeypatch, tmp_path):
    context, update, groups = setup_menu(monkeypatch, tmp_path, count=107)
    active = peak = 0

    async def check(chat_id, bot_id):
        nonlocal active, peak
        update.message.reply_text.assert_awaited_once()
        assert "正在加载" in update.message.reply_text.await_args.args[0]
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return SimpleNamespace(status="administrator", can_delete_messages=True)

    context.bot.get_chat_member.side_effect = check
    asyncio.run(menu.start_cleanup_menu(update, context))

    assert peak == 5
    assert active == 0
    assert context.user_data["cleanup_selection"]["groups"] == groups
    update.callback_query.message.edit_text.assert_awaited_once()
    context.bot.delete_messages.assert_not_awaited()


@pytest.mark.parametrize("timeout_scope", ["single", "menu"])
def test_menu_timeout_keeps_verified_groups_and_cancels_pending_queries(monkeypatch, tmp_path, timeout_scope):
    context, update, groups = setup_menu(monkeypatch, tmp_path)
    monkeypatch.setattr(menu, "PERMISSION_QUERY_TIMEOUT" if timeout_scope == "single" else "MENU_LOAD_TIMEOUT", 0.02)
    active = 0

    async def check(chat_id, bot_id):
        nonlocal active
        if chat_id == groups[0]["chat_id"]:
            return SimpleNamespace(status="administrator", can_delete_messages=True)
        active += 1
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    context.bot.get_chat_member.side_effect = check
    asyncio.run(menu.start_cleanup_menu(update, context))

    assert active == 0
    assert context.user_data["cleanup_selection"]["groups"] == groups[:1]
    context.bot.delete_messages.assert_not_awaited()


def test_permission_rate_limit_stops_queued_queries_and_repeated_commands(monkeypatch, tmp_path):
    context, update, _ = setup_menu(monkeypatch, tmp_path, count=30)
    context.bot.get_chat_member.side_effect = RetryAfter(30)

    async def run():
        await menu.start_cleanup_menu(update, context)
        count = context.bot.get_chat_member.await_count
        assert count <= 5
        assert "cleanup_selection" not in context.user_data
        await menu.start_cleanup_menu(update, context)
        assert context.bot.get_chat_member.await_count == count
        assert "暂受限" in update.message.reply_text.await_args.args[0]

    asyncio.run(run())
    context.bot.delete_messages.assert_not_awaited()


def test_menu_multiselect_cancel_and_broadcast_state_are_independent(monkeypatch, tmp_path):
    context, update, _ = setup_menu(monkeypatch, tmp_path)
    context.user_data["broadcast_selected"] = {-999}

    async def run():
        await handler.delete_group_messages_command(update, context)
        await click(update, context, "toggle:-100")
        await click(update, context, "toggle:-101")
        state = context.user_data["cleanup_selection"]
        assert state["selected"] == {-100, -101}
        labels = [r[0].text for r in menu.selection_keyboard(state).inline_keyboard[:-1]]
        assert labels == ["√ 群 0", "√ 群 1", "□ 群 2"]
        await click(update, context, "toggle:-100")
        assert state["selected"] == {-101}
        await click(update, context, "cancel")
        assert "cleanup_selection" not in context.user_data

    asyncio.run(run())
    context.bot.delete_messages.assert_not_awaited()
    assert context.user_data["broadcast_selected"] == {-999}


def test_only_confirmed_selected_groups_are_deleted_and_callback_cannot_replay(monkeypatch, tmp_path):
    context, update, _ = setup_menu(monkeypatch, tmp_path)

    async def run():
        await menu.start_cleanup_menu(update, context)
        await click(update, context, "toggle:-100")
        await click(update, context, "toggle:-102")
        await click(update, context, "confirm")
        context.bot.delete_messages.assert_not_awaited()
        await click(update, context, "next")
        assert "群 0" in update.callback_query.edit_message_text.await_args.args[0]
        assert "群 2" in update.callback_query.edit_message_text.await_args.args[0]
        context.bot.delete_messages.assert_not_awaited()
        await click(update, context, "confirm")
        context.bot_data["group_message_positions"].record_result(
            {"chat": {"id": -100, "type": "supergroup"}, "message_id": 99}
        )
        tasks = list(context.bot_data["private_message_cleanup_tasks"].values())
        await menu.handle_cleanup_callback(update, context)
        assert update.callback_query.answer.await_args.kwargs["show_alert"] is True
        await asyncio.gather(*tasks)
        assert "完成 2 个群" in update.callback_query.edit_message_text.await_args.args[0]

    asyncio.run(run())
    assert {c.kwargs["chat_id"] for c in context.bot.delete_messages.await_args_list} == {-100, -102}
    assert all(c.kwargs["message_ids"] == [5, 4, 3, 2, 1] for c in context.bot.delete_messages.await_args_list)
    context.bot.send_message.assert_not_awaited()
    assert update.message.reply_text.await_count == 1


@pytest.mark.parametrize("invalid", ["owner", "group", "old_menu", "wrong_message", "unknown_group"])
def test_invalid_callbacks_never_delete(monkeypatch, tmp_path, invalid):
    context, update, _ = setup_menu(monkeypatch, tmp_path)

    async def run():
        await menu.start_cleanup_menu(update, context)
        token = context.user_data["cleanup_selection"]["token"]
        update.callback_query.data = f"cleanup:{token}:toggle:-9999"
        if invalid == "owner":
            monkeypatch.setattr(menu, "is_owner_update", lambda update: False)
        elif invalid == "group":
            update.effective_chat.type = "supergroup"
        elif invalid == "old_menu":
            await menu.start_cleanup_menu(update, context)
        elif invalid == "wrong_message":
            update.callback_query.message = SimpleNamespace(message_id=49)
        await menu.handle_cleanup_callback(update, context)
        assert context.user_data["cleanup_selection"]["selected"] == set()

    asyncio.run(run())
    context.bot.delete_messages.assert_not_awaited()


def test_pagination_retains_selections_and_back_preserves_confirmation(monkeypatch, tmp_path):
    context, update, _ = setup_menu(monkeypatch, tmp_path, count=25)

    async def run():
        await menu.start_cleanup_menu(update, context)
        await click(update, context, "toggle:-100")
        await click(update, context, "page:1")
        state = context.user_data["cleanup_selection"]
        assert menu.selection_keyboard(state).inline_keyboard[0][0].text == "□ 群 20"
        await click(update, context, "toggle:-124")
        await click(update, context, "next")
        await click(update, context, "back")
        assert state["selected"] == {-100, -124}
        assert state["stage"] == "select"

    asyncio.run(run())


def test_unknown_positions_and_missing_permissions_are_reported_privately(monkeypatch, tmp_path):
    context, update, groups = setup_menu(monkeypatch, tmp_path)
    context.bot.get_chat_member.side_effect = [SimpleNamespace(status="member"), Forbidden("gone")]
    context.bot_data["private_message_cleanup_tasks"] = {}
    asyncio.run(menu.run_selected_cleanup(update.callback_query, context, "x", groups, {-100: 0, -101: 5, -102: 5}))
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "尚无消息记录" in text and "没有删除权限" in text and "无法访问群" in text
    context.bot.delete_messages.assert_not_awaited()
    context.bot.send_message.assert_not_awaited()


def test_shutdown_cancels_private_cleanup_and_its_group_work(monkeypatch, tmp_path):
    context, update, groups = setup_menu(monkeypatch, tmp_path, count=4)
    started = asyncio.Event()
    wait = asyncio.Event()

    async def delete_messages(**kwargs):
        started.set()
        await wait.wait()

    context.bot.delete_messages.side_effect = delete_messages

    async def run():
        task = asyncio.create_task(menu.run_selected_cleanup(update.callback_query, context, "x", groups, {g["chat_id"]: 5 for g in groups}))
        context.bot_data["private_message_cleanup_tasks"] = {"x": task}
        await started.wait()
        await stop_managed_background_tasks(SimpleNamespace(bot_data=context.bot_data))
        assert task.cancelled()
        assert "group_message_cleanup_tasks" not in context.bot_data

    asyncio.run(run())


def test_positions_persist_incoming_outgoing_and_album_ids_without_message_text(tmp_path):
    path = tmp_path / "positions.sqlite3"
    positions = GroupMessagePositions(path)
    group = {"id": -100, "type": "group"}
    positions.record_result([{"update_id": 1, "message": {"chat": group, "message_id": 10, "text": "PRIVATE CARD TEXT"}}])
    positions.record_result({"chat": group, "message_id": 11})
    positions.record_result([{"chat": group, "message_id": 12}, {"chat": group, "message_id": 13}])
    positions.record_result([{"edited_message": {"chat": group, "message_id": 9}}])
    positions.record_result({"chat": {"id": 1, "type": "private"}, "message_id": 99})
    assert GroupMessagePositions(path).latest(-100) == 13
    assert positions.latest(1) == 0
    assert b"PRIVATE CARD TEXT" not in path.read_bytes()


def test_request_preserves_original_response_even_if_recording_fails(monkeypatch, tmp_path):
    payload = json.dumps({"ok": True, "result": {"chat": {"id": -100, "type": "group"}, "message_id": 7}}).encode()
    monkeypatch.setattr(HTTPXRequest, "do_request", AsyncMock(return_value=(200, payload)))
    positions = GroupMessagePositions(tmp_path / "positions.sqlite3")
    request = PositionTrackingRequest(positions=positions)

    async def run():
        assert await request.do_request(url="offline", method="POST") == (200, payload)
        assert positions.latest(-100) == 7
        monkeypatch.setattr(positions, "record_result", lambda value: (_ for _ in ()).throw(OSError("disk")))
        assert await request.do_request(url="offline", method="POST") == (200, payload)
        await request.shutdown()

    asyncio.run(run())


def test_application_tracks_polling_and_outgoing_messages(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123:offline-test")
    monkeypatch.setenv("LEDGER_DB_PATH", str(tmp_path / "ledger.sqlite3"))
    app = build_telegram_application(register_handlers=lambda app: None, post_init=AsyncMock(), post_shutdown=AsyncMock())
    assert isinstance(app.bot.request, PositionTrackingRequest)
    assert all(isinstance(r, PositionTrackingRequest) for r in app.bot._request)
    assert all(r.positions is app.bot_data["group_message_positions"] for r in app.bot._request)
    assert app.bot.request._client_kwargs["limits"].max_connections >= 5
