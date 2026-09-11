from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

import pytest

from services.ledger import ledger_commands
from storage.repositories import ledger_storage


ACTOR = ledger_commands.Actor(7, "boss", "Boss")


def command(store, text, message_id=None, chat_id=-1001):
    return ledger_commands.handle_text(store, chat_id, ACTOR, text, {7}, message_id=message_id)


@pytest.mark.parametrize("text", ["+100", "下发100", "-100"])
def test_message_replay_is_silent_and_distinct_messages_still_count(tmp_path, text):
    path = tmp_path / "ledger.sqlite3"
    store = ledger_storage.LedgerStore(path)
    assert command(store, text, 1).changed
    assert command(store, text, 1).text == ""
    assert command(store, text, 2).changed
    assert command(store, text, 1, chat_id=-2002).changed
    assert len(store.entries(-1001)) == 2
    store.void_entry(-1001, store.entries(-1001)[0].id)
    store.close()
    store = ledger_storage.LedgerStore(path)
    assert command(store, text, 1).text == ""
    assert len(store.entries(-1001)) == 1
    store.clear_entries(-1001)
    assert command(store, text, 2).text == ""
    assert store.entries(-1001) == []
    assert command(store, text, 3).changed
    store.close()


def test_receipt_rolls_back_when_entry_insert_fails(tmp_path):
    store = ledger_storage.LedgerStore(tmp_path / "ledger.sqlite3")
    store.conn.execute("CREATE TRIGGER fail_entry BEFORE INSERT ON entries BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises(sqlite3.IntegrityError):
        command(store, "+100", 1)
    store.conn.execute("DROP TRIGGER fail_entry")
    assert command(store, "+100", 1).changed
    assert len(store.entries(-1001)) == 1
    store.close()


def test_concurrent_delivery_records_one_entry(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger_storage.LedgerStore(path).close()
    barrier = Barrier(2)

    def deliver():
        store = ledger_storage.LedgerStore(path)
        barrier.wait(timeout=10)
        try:
            return command(store, "+100", 1).changed
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: deliver(), range(2)))
    assert sorted(results) == [False, True]


def test_legacy_receipts_preserve_existing_duplicate_history(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    store = ledger_storage.LedgerStore(path)
    command(store, "+100", 1)
    command(store, "+100", 2)
    store.conn.execute("UPDATE entries SET source_message_id=1")
    store.conn.execute("DELETE FROM ledger_entry_messages")
    store.conn.commit()
    original = store.entries(-1001)
    store.close()
    store = ledger_storage.LedgerStore(path)
    assert command(store, "+100", 1).text == ""
    assert store.entries(-1001) == original
    store.close()


@pytest.mark.parametrize("old_hour,new_hour,now_hour", [(0, 3, 1), (3, 0, 4), (3, 5, 1), (5, 1, 2), (3, 1, 12)])
def test_cutoff_change_preserves_current_and_previous_until_new_boundary(tmp_path, monkeypatch, old_hour, new_hour, now_hour):
    class Clock(datetime):
        current = datetime(2026, 9, 12, now_hour, tzinfo=ledger_storage.LEDGER_TZ)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(ledger_storage, "datetime", Clock)
    path = tmp_path / "ledger.sqlite3"
    store = ledger_storage.LedgerStore(path)
    store.set_ledger_reset_hour(-1001, old_hour)
    command(store, "+90 昨日", 1)
    store.conn.execute("UPDATE entries SET accounting_date=?", (store.previous_accounting_date(-1001),))
    store.conn.commit()
    command(store, "+100 当前", 2)
    original = store.entries(-1001)
    before = command(store, "+0").text
    yesterday = command(store, "昨日账单").text
    store.set_ledger_reset_hour(-1001, new_hour)
    boundary = store.next_cutoff_at(-1001)
    assert command(store, "+0").text == before
    assert command(store, "昨日账单").text == yesterday
    store.close()
    store = ledger_storage.LedgerStore(path)
    assert command(store, "+0").text == before
    Clock.current = boundary - timedelta(seconds=1)
    command(store, "+20 日切前", 3)
    assert "总入款金额：120" in command(store, "+0").text
    Clock.current = boundary
    assert "总入款金额：0" in command(store, "+0").text
    assert "总入款金额：120" in command(store, "昨日账单").text
    command(store, "+30 日切后", 4)
    first_key = store.current_accounting_date(-1001)
    Clock.current += timedelta(days=1)
    assert store.previous_accounting_date(-1001) == first_key
    assert "总入款金额：30" in command(store, "昨日账单").text
    assert "总入款金额：0" in command(store, "+0").text
    Clock.current += timedelta(days=1)
    assert "总入款金额：0" in command(store, "昨日账单").text
    assert store.entries(-1001)[:2] == original
    store.close()


def test_repeated_cutoff_change_keeps_latest_period_and_previous(tmp_path, monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 9, 12, 1, tzinfo=ledger_storage.LEDGER_TZ)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(ledger_storage, "datetime", Clock)
    store = ledger_storage.LedgerStore(tmp_path / "ledger.sqlite3")
    store.set_ledger_reset_hour(-1001, 0)
    command(store, "+100", 1)
    store.set_ledger_reset_hour(-1001, 3)
    store.set_ledger_reset_hour(-1001, 5)
    Clock.current = Clock.current.replace(hour=3)
    assert "总入款金额：100" in command(store, "+0").text
    Clock.current = Clock.current.replace(hour=5)
    command(store, "+20", 2)
    store.set_ledger_reset_hour(-1001, 6)
    assert "总入款金额：100" in command(store, "昨日账单").text
    Clock.current = Clock.current.replace(hour=6)
    assert "总入款金额：0" in command(store, "+0").text
    assert "总入款金额：20" in command(store, "昨日账单").text
    store.close()
