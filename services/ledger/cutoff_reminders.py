from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from telegram.error import RetryAfter

from services.ledger.ledger_commands import _summarize_entries
from storage.repositories.ledger_storage import LEDGER_TZ, LedgerStore


def format_cutoff_reminder(cutoff_at: datetime, balance: Decimal) -> str:
    cutoff_at = cutoff_at.astimezone(LEDGER_TZ)
    return (
        f"📝系统 {cutoff_at:%H:%M} 日切账单\n"
        f"▫️时间截: {cutoff_at:%Y-%m-%d %H:%M:%S}\n"
        f"▫️余款:  {abs(balance):.2f}"
    )


def initialize_schedule(store: LedgerStore, now: datetime) -> None:
    now = now.astimezone(LEDGER_TZ)
    starts = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if starts < now:
        starts += timedelta(days=1)
    with store.conn:
        store.conn.execute(
            "INSERT OR IGNORE INTO ledger_reminder_schedule VALUES (1, ?)",
            (starts.isoformat(),),
        )


async def send_due_reminders(bot: Any, store: LedgerStore, now: datetime, logger: logging.Logger) -> int:
    """Evaluate the period closed at today's 09:00; never include the open period."""
    now = now.astimezone(LEDGER_TZ)
    due = now.replace(hour=9, minute=0, second=0, microsecond=0)
    row = store.conn.execute("SELECT starts_at FROM ledger_reminder_schedule WHERE id = 1").fetchone()
    if row is None or now < due or due < datetime.fromisoformat(row["starts_at"]):
        return 0
    sent = 0
    for group in store.list_active_bot_groups():
        chat_id = int(group["chat_id"])
        if not store.is_ledger_enabled(chat_id):
            continue
        closed = store.latest_closed_period(chat_id, due)
        if closed is None:
            continue
        period, cutoff_at = closed
        if store.conn.execute(
            "SELECT 1 FROM ledger_cutoff_reminders WHERE chat_id = ? AND accounting_date = ?",
            (chat_id, period),
        ).fetchone():
            continue
        entries = store.entries(chat_id, accounting_date=period)
        balance = _summarize_entries(store, chat_id, entries).balance_usdt
        # Reserve before Telegram I/O: an ambiguous timeout must not cause duplicate reminders.
        with store.conn:
            claimed = store.conn.execute(
                "INSERT OR IGNORE INTO ledger_cutoff_reminders "
                "(chat_id, accounting_date, cutoff_at, balance_usdt, status) VALUES (?, ?, ?, ?, ?)",
                (chat_id, period, cutoff_at.isoformat(), str(balance), "sending" if balance < 0 else "skipped"),
            ).rowcount
        if not claimed or balance >= 0:
            continue
        try:
            while True:
                try:
                    message = await bot.send_message(chat_id=chat_id, text=format_cutoff_reminder(cutoff_at, balance))
                    break
                except RetryAfter as exc:
                    delay = exc.retry_after
                    await asyncio.sleep(delay.total_seconds() if isinstance(delay, timedelta) else float(delay))
        except Exception as exc:
            with store.conn:
                store.conn.execute(
                    "UPDATE ledger_cutoff_reminders SET status = 'unconfirmed' WHERE chat_id = ? AND accounting_date = ?",
                    (chat_id, period),
                )
            logger.warning("Ledger cutoff reminder delivery unconfirmed (%s)", type(exc).__name__)
            continue
        with store.conn:
            store.conn.execute(
                "UPDATE ledger_cutoff_reminders SET status = 'sent', message_id = ? WHERE chat_id = ? AND accounting_date = ?",
                (message.message_id, chat_id, period),
            )
        sent += 1
    return sent


async def ledger_cutoff_reminder_loop(bot: Any, store: LedgerStore, *, logger: logging.Logger) -> None:
    initialize_schedule(store, datetime.now(LEDGER_TZ))
    while True:
        try:
            await send_due_reminders(bot, store, datetime.now(LEDGER_TZ), logger)
        except Exception:
            logger.exception("Ledger cutoff reminder check failed")
        now = datetime.now(LEDGER_TZ)
        # Align checks to the minute so the scheduled check begins at 09:00.
        await asyncio.sleep(60 - now.second - now.microsecond / 1_000_000)
