from datetime import datetime

import pytest

from services.ledger import ledger_commands
from storage.repositories import ledger_storage


@pytest.mark.parametrize("hour,now_hour,start_day,end_day", [(3, 2, 13, 14), (3, 3, 14, 15), (5, 14, 14, 15)])
def test_cutoff_status_displays_actual_period_range(tmp_path, monkeypatch, hour, now_hour, start_day, end_day):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 14, now_hour, tzinfo=ledger_storage.LEDGER_TZ).astimezone(tz)

    monkeypatch.setattr(ledger_storage, "datetime", Clock)
    store = ledger_storage.LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        store.set_ledger_reset_hour(-1001, hour)
        text = ledger_commands._format_cutoff_status(store, -1001)
        assert f"当前账期：2026-09-{start_day:02d} {hour:02d}:00 至 2026-09-{end_day:02d} {hour:02d}:00" in text
        assert f"下次日切：2026-09-{end_day:02d} {hour:02d}:00" in text
    finally:
        store.close()


def test_cutoff_status_keeps_old_start_during_transition_and_restart(tmp_path, monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 9, 14, 14, tzinfo=ledger_storage.LEDGER_TZ)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(ledger_storage, "datetime", Clock)
    path = tmp_path / "ledger.sqlite3"
    store = ledger_storage.LedgerStore(path)
    store.add_entry(-1001, "income", "100", "U", "", 1, "Test")
    original = store.entries(-1001)
    store.set_ledger_reset_hour(-1001, 5)
    store.close()
    store = ledger_storage.LedgerStore(path)
    try:
        assert "当前账期：2026-09-14 03:00 至 2026-09-15 05:00" in ledger_commands._format_cutoff_status(store, -1001)
        Clock.current = datetime(2026, 9, 15, 5, tzinfo=ledger_storage.LEDGER_TZ)
        assert "当前账期：2026-09-15 05:00 至 2026-09-16 05:00" in ledger_commands._format_cutoff_status(store, -1001)
        assert store.entries(-1001) == original
    finally:
        store.close()


@pytest.mark.parametrize("view_mode", ["compact", "detailed"])
@pytest.mark.parametrize("cutoff_hour", [2, 3])
def test_full_bill_resets_and_yesterday_keeps_previous_period(tmp_path, monkeypatch, view_mode, cutoff_hour):
    class Clock(datetime):
        current = datetime(2026, 9, 8, cutoff_hour - 1, 59, tzinfo=ledger_storage.LEDGER_TZ)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(ledger_storage, "datetime", Clock)
    store = ledger_storage.LedgerStore(tmp_path / "ledger.sqlite3")
    actor = ledger_commands.Actor(7, "boss", "Boss")

    def command(text):
        return ledger_commands.handle_text(store, -1001, actor, text, {7}).text

    try:
        if cutoff_hour != 3:
            store.set_ledger_reset_hour(-1001, cutoff_hour)
        assert store.get_ledger_reset_hour(-1001) == cutoff_hour
        store.set_ledger_view_mode(-1001, view_mode)
        command("+999 更早账期")

        Clock.current = datetime(2026, 9, 9, cutoff_hour - 1, 59, 59, tzinfo=ledger_storage.LEDGER_TZ)
        command("+100 上期入款")
        command("下发40 上期下发")
        before = command("+0")
        assert "总入款金额：100" in before
        assert "更早账期" not in before

        Clock.current = datetime(2026, 9, 9, cutoff_hour, 0, tzinfo=ledger_storage.LEDGER_TZ)
        for text in ("+0", "今日账单", "完整账单", "全部账单", "总账单", "/fullbill"):
            bill = command(text)
            assert "总入款金额：0" in bill
            assert "已入款(0笔)" in bill
            assert "已下发(0笔)" in bill
            assert "上期" not in bill
            assert "更早账期" not in bill

        command("+73 本期入款")
        command("下发10 本期下发")
        for text in ("+0", "今日账单"):
            bill = command(text)
            assert "总入款金额：73" in bill
            assert "已下发：10U" in bill
            assert "已入款(1笔)" in bill
            assert "已下发(1笔)" in bill
            assert "本期入款" in bill
            assert "上期" not in bill
            assert "更早账期" not in bill

        yesterday = command("昨日账单")
        assert "总入款金额：100" in yesterday
        assert "已下发：40U" in yesterday
        assert "上期入款" in yesterday
        assert "本期" not in yesterday
        assert "更早账期" not in yesterday
        assert len(store.entries(-1001)) == 5
    finally:
        store.close()


@pytest.mark.parametrize("override", [0, 2, 5])
def test_manual_cutoff_survives_restart(tmp_path, override):
    path = tmp_path / "ledger.sqlite3"
    store = ledger_storage.LedgerStore(path)
    try:
        assert store.get_ledger_reset_hour(-1001) == 3
        store.set_ledger_reset_hour(-1001, override)
    finally:
        store.close()

    store = ledger_storage.LedgerStore(path)
    try:
        store.ensure_chat(-1001)
        assert store.get_ledger_reset_hour(-1001) == override
        assert store.get_ledger_reset_hour(-2002) == 3
    finally:
        store.close()
