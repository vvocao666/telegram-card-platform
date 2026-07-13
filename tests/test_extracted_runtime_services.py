from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from services.group.lifecycle_service import (
    GroupLifecycleHooks,
    handle_bot_chat_member,
    handle_left_chat_member,
    handle_new_chat_members,
)
from services.ledger.telegram_service import LedgerTextHooks, handle_ledger_text
from services.ocr.history_service import CardHistoryDuplicate, CardHistoryHooks, append_history_duplicates
from services.status.remote_metrics import record_remote_ocr_status


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.caption = None
        self.message_id = 10
        self.reply_to_message = None
        self.replies: list[str] = []

    async def reply_text(self, text: str, **_kwargs) -> None:
        self.replies.append(text)


def test_history_service_formats_duplicate_without_runtime_import() -> None:
    hooks = CardHistoryHooks(
        store=object(),
        ledger_timezone=timezone.utc,
        fuzzy_suffix=" fuzzy",
        result_card_lines=lambda _results: ([], []),
        user_label=lambda _update: "",
        format_card=lambda card: f"<{card}>",
    )
    text = append_history_duplicates(
        "result",
        [CardHistoryDuplicate("PUBG", "S07336-ABCD-EFGH-IJKLM", "2026-07-13T12:00:00+00:00", "Name | @user |")],
        hooks,
    )
    assert "<S07336-ABCD-EFGH-IJKLM>" in text
    assert "来自 | @user |" in text


def test_remote_metrics_updates_success_counters() -> None:
    status = {
        "today_remote_success": 0,
        "today_remote_failed": 0,
        "today_remote_latency_total_ms": 0,
        "today_enhanced_used": 0,
        "today_cache_hits": 0,
    }
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    record_remote_ocr_status(
        status=status,
        logger=SimpleNamespace(info=lambda *_args: None),
        now_factory=lambda: now,
        ensure_today=lambda _now: None,
        ok=True,
        latency_ms=120,
        card_count=2,
        cache_hit=True,
    )
    assert status["today_remote_success"] == 1
    assert status["today_remote_latency_total_ms"] == 120
    assert status["today_cache_hits"] == 1
    assert status["last_success_at"] == "2026-07-13T12:00:00+00:00"


def test_ledger_text_service_keeps_recognition_toggle_behavior() -> None:
    message = FakeMessage("关闭识别")
    update = SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=-100),
        effective_user=SimpleNamespace(id=7),
    )
    enabled: list[tuple[int, bool]] = []
    hooks = LedgerTextHooks(
        store=SimpleNamespace(set_recognition_enabled=lambda chat_id, value: enabled.append((chat_id, value))),
        remember_bot_chat=lambda _update: None,
        remember_ledger_user=lambda _update: None,
        ensure_private_owner=lambda _update: None,
        owner_ids=lambda _chat_id: {7},
        extract_trc20_address=lambda _text: None,
        reply_trc20_verify_image=lambda *_args: None,
        set_realtime_rate=lambda _update: _false_async(),
        is_price_command=lambda _text: False,
        reply_okx_price=lambda _message: _none_async(),
        calculate_expression=lambda _text: None,
        actor_from_update=lambda _update: None,
        actor_from_message=lambda _message: None,
        handle_command_text=lambda **_kwargs: None,
        reply_ledger=lambda *_args: _none_async(),
    )
    assert asyncio.run(handle_ledger_text(update, hooks)) is True
    assert enabled == [(-100, False)]
    assert message.replies == ["卡密识别已关闭，后续图片不会识别卡密。发送“开启识别”可重新开启。"]


async def _false_async() -> bool:
    return False


async def _none_async() -> None:
    return None


def test_group_lifecycle_service_initializes_and_welcomes_once() -> None:
    calls: list[tuple] = []
    store = SimpleNamespace(
        remember_bot_chat=lambda *args: calls.append(("remember", *args)),
        ensure_chat=lambda *args: calls.append(("ensure", *args)),
        set_chat_owner=lambda *args: calls.append(("owner", *args)),
    )
    bot = SimpleNamespace(send_message=lambda **kwargs: _capture_async(calls, kwargs))
    update = SimpleNamespace(
        my_chat_member=SimpleNamespace(
            old_chat_member=SimpleNamespace(status="left"),
            new_chat_member=SimpleNamespace(status="member"),
        ),
        effective_chat=SimpleNamespace(id=-200, type="group", title="Group"),
        effective_user=SimpleNamespace(id=8),
    )
    sent_at: dict[int, float] = {}
    hooks = GroupLifecycleHooks(store=store, welcome_sent_at=sent_at, welcome_message=lambda: "welcome", monotonic=lambda: 1000.0)
    asyncio.run(handle_bot_chat_member(update, SimpleNamespace(bot=bot), hooks))
    asyncio.run(handle_bot_chat_member(update, SimpleNamespace(bot=bot), hooks))
    assert calls.count(("ensure", -200)) == 1
    assert len([call for call in calls if call[0] == "send"]) == 1


async def _capture_async(calls: list[tuple], payload: dict) -> None:
    calls.append(("send", payload))


def test_member_join_and_leave_messages_are_safe_and_distinct() -> None:
    calls: list[tuple] = []
    store = SimpleNamespace(set_chat_owner=lambda *args: calls.append(("owner", *args)))
    hooks = GroupLifecycleHooks(store=store, welcome_sent_at={}, welcome_message=lambda: "welcome")
    member = SimpleNamespace(
        id=22,
        is_bot=False,
        username=None,
        full_name="A < B",
        first_name="A",
        last_name="B",
    )
    message = SimpleNamespace(new_chat_members=[member], left_chat_member=member)
    update = SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=-300),
        effective_user=SimpleNamespace(id=9),
    )
    bot = SimpleNamespace(send_message=lambda **kwargs: _capture_async(calls, kwargs))
    context = SimpleNamespace(bot=bot)

    asyncio.run(handle_new_chat_members(update, context, hooks, bot_user_id=99))
    asyncio.run(handle_left_chat_member(update, context, hooks, bot_user_id=99))

    sent = [call[1] for call in calls if call[0] == "send"]
    assert sent[0]["text"] == '💐欢迎<a href="tg://user?id=22">A &lt; B</a>加入该群~'
    assert sent[1]["text"] == '<a href="tg://user?id=22">A &lt; B</a>离开了本群，聚是满天星，散是一团火~'
    assert all(payload["parse_mode"] == "HTML" for payload in sent)


def test_member_lifecycle_skips_bot_accounts_and_sets_inviter_for_own_bot() -> None:
    calls: list[tuple] = []
    store = SimpleNamespace(set_chat_owner=lambda *args: calls.append(("owner", *args)))
    hooks = GroupLifecycleHooks(store=store, welcome_sent_at={}, welcome_message=lambda: "welcome")
    own_bot = SimpleNamespace(id=99, is_bot=True)
    other_bot = SimpleNamespace(id=100, is_bot=True)
    update = SimpleNamespace(
        message=SimpleNamespace(new_chat_members=[own_bot, other_bot], left_chat_member=other_bot),
        effective_chat=SimpleNamespace(id=-300),
        effective_user=SimpleNamespace(id=9),
    )
    bot = SimpleNamespace(send_message=lambda **kwargs: _capture_async(calls, kwargs))
    context = SimpleNamespace(bot=bot)

    asyncio.run(handle_new_chat_members(update, context, hooks, bot_user_id=99))
    asyncio.run(handle_left_chat_member(update, context, hooks, bot_user_id=99))

    assert calls == [("owner", -300, 9)]
