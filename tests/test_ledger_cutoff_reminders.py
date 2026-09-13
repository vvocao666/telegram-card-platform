import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import RetryAfter, TimedOut

from services.ledger import cutoff_reminders as reminders
from storage.repositories import ledger_storage


TZ = ledger_storage.LEDGER_TZ
LOGGER = logging.getLogger(__name__)


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 9, 13, 2, 59, 59, tzinfo=TZ)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(ledger_storage, "datetime", Clock)
    return Clock


def add(store, amount, kind="income", chat=-1001):
    return store.add_entry(chat, kind, amount, "U", "", 1, "Tester")


def setup_store(path, clock):
    store = ledger_storage.LedgerStore(path)
    store.remember_bot_chat(-1001, "Test", "supergroup")
    reminders.initialize_schedule(store, clock.current)
    return store


def send(bot, store, clock):
    return asyncio.run(reminders.send_due_reminders(bot, store, clock.current, LOGGER))


@pytest.mark.parametrize("payout,expected", [(488, 1), (100, 0), (99, 0)])
def test_only_negative_closed_balance_at_nine_and_no_repeat(tmp_path, clock, payout, expected):
    path = tmp_path / "ledger.sqlite3"
    store = setup_store(path, clock)
    add(store, 100)
    add(store, payout, "payout")
    clock.current = clock.current.replace(hour=3, minute=0, second=0)
    # Exact-cutoff entries belong to the next period; even huge payouts cannot affect this reminder.
    add(store, 9000, "payout")
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=42)))
    clock.current = clock.current.replace(hour=8, minute=59, second=59)
    assert send(bot, store, clock) == 0
    clock.current = clock.current.replace(hour=9, minute=0, second=0)
    before = store.entries(-1001)
    assert send(bot, store, clock) == expected
    assert store.entries(-1001) == before
    if expected:
        assert bot.send_message.call_args.kwargs == {
            "chat_id": -1001,
            "text": "📝系统 03:00 日切账单\n▫️时间截: 2026-09-13 03:00:00\n▫️余款:  388.00",
        }
    store.close()
    store = ledger_storage.LedgerStore(path)
    reminders.initialize_schedule(store, clock.current)
    assert send(bot, store, clock) == 0
    assert bot.send_message.call_count == expected
    store.close()


def test_custom_noon_cutoff_uses_yesterdays_noon_and_snapshot_rates(tmp_path, clock):
    clock.current = datetime(2026, 9, 12, 11, tzinfo=TZ)
    store = setup_store(tmp_path / "ledger.sqlite3", clock)
    store.set_ledger_reset_hour(-1001, 12)
    store.set_rate(-1001, 2)
    store.set_fee_percent(-1001, 10)
    add(store, 100)  # 45 U payable
    add(store, 50, "payout")
    clock.current = datetime(2026, 9, 13, 9, tzinfo=TZ)
    add(store, 800)  # Still-open noon period
    store.set_rate(-1001, 5)
    store.set_fee_percent(-1001, 0)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    assert send(bot, store, clock) == 1
    assert bot.send_message.call_args.kwargs["text"] == (
        "📝系统 12:00 日切账单\n▫️时间截: 2026-09-12 12:00:00\n▫️余款:  5.00"
    )
    store.close()


def test_cutoff_change_preserves_actual_closed_time_and_transition_key(tmp_path, clock):
    store = setup_store(tmp_path / "ledger.sqlite3", clock)
    add(store, 10, "payout")
    clock.current = clock.current.replace(hour=4)
    add(store, 20, "payout")
    store.set_ledger_reset_hour(-1001, 12)
    clock.current = datetime(2026, 9, 13, 9, tzinfo=TZ)
    assert store.latest_closed_period(-1001, clock.current) == (
        "2026-09-12", datetime(2026, 9, 13, 3, tzinfo=TZ)
    )
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    assert send(bot, store, clock) == 1
    assert "余款:  10.00" in bot.send_message.call_args.kwargs["text"]
    clock.current = datetime(2026, 9, 14, 9, tzinfo=TZ)
    assert send(bot, store, clock) == 1
    assert "2026-09-13 12:00:00" in bot.send_message.call_args.kwargs["text"]
    assert "余款:  20.00" in bot.send_message.call_args.kwargs["text"]
    store.close()


def test_first_install_after_nine_does_not_broadcast_old_bills(tmp_path, clock):
    store = setup_store(tmp_path / "ledger.sqlite3", clock)
    add(store, 50, "payout")
    store.conn.execute("DELETE FROM ledger_reminder_schedule")
    store.conn.commit()
    clock.current = datetime(2026, 9, 13, 10, tzinfo=TZ)
    reminders.initialize_schedule(store, clock.current)
    bot = SimpleNamespace(send_message=AsyncMock())
    assert send(bot, store, clock) == 0
    clock.current += timedelta(days=1)
    # An empty period does not repeat the old negative balance.
    assert send(bot, store, clock) == 0
    bot.send_message.assert_not_called()
    store.close()


def test_group_isolation_disabled_inactive_private_and_voided_entries(tmp_path, clock):
    store = setup_store(tmp_path / "ledger.sqlite3", clock)
    for chat in (-1001, -1002, -1003, 1004, -1005):
        store.remember_bot_chat(chat, "Test", "private" if chat > 0 else "group")
        entry = add(store, 20, "payout", chat)
        if chat == -1005:
            store.void_entry(chat, entry.id)
    store.set_ledger_enabled(-1002, False)
    store.conn.execute("UPDATE bot_chats SET is_active = 0 WHERE chat_id = -1003")
    store.conn.commit()
    clock.current = datetime(2026, 9, 13, 9, tzinfo=TZ)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    assert send(bot, store, clock) == 1
    assert bot.send_message.call_args.kwargs["chat_id"] == -1001
    store.close()


def test_ambiguous_timeout_not_resent_and_other_groups_continue(tmp_path, clock):
    store = setup_store(tmp_path / "ledger.sqlite3", clock)
    store.remember_bot_chat(-1002, "ZTest", "group")
    add(store, 10, "payout")
    add(store, 10, "payout", -1002)
    clock.current = datetime(2026, 9, 13, 9, tzinfo=TZ)
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[TimedOut(), SimpleNamespace(message_id=1)]))
    assert send(bot, store, clock) == 1
    assert send(bot, store, clock) == 0
    assert bot.send_message.call_count == 2
    store.close()


def test_retry_after_waits_before_retry(tmp_path, clock, monkeypatch):
    store = setup_store(tmp_path / "ledger.sqlite3", clock)
    add(store, 10, "payout")
    clock.current = datetime(2026, 9, 13, 9, tzinfo=TZ)
    sleeper = AsyncMock()
    monkeypatch.setattr(reminders.asyncio, "sleep", sleeper)
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[RetryAfter(2), SimpleNamespace(message_id=1)]))
    assert send(bot, store, clock) == 1
    sleeper.assert_awaited_once_with(2.0)
    assert send(bot, store, clock) == 0
    store.close()
