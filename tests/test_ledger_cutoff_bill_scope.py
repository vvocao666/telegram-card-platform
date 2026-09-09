from datetime import datetime

import pytest

from services.ledger import ledger_commands
from storage.repositories import ledger_storage


@pytest.mark.parametrize("view_mode", ["compact", "detailed"])
def test_full_bill_resets_at_two_and_yesterday_keeps_previous_period(tmp_path, monkeypatch, view_mode):
    class Clock(datetime):
        current = datetime(2026, 9, 8, 1, 59, tzinfo=ledger_storage.LEDGER_TZ)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(ledger_storage, "datetime", Clock)
    store = ledger_storage.LedgerStore(tmp_path / "ledger.sqlite3")
    actor = ledger_commands.Actor(7, "boss", "Boss")

    def command(text):
        return ledger_commands.handle_text(store, -1001, actor, text, {7}).text

    try:
        store.set_ledger_reset_hour(-1001, 2)
        store.set_ledger_view_mode(-1001, view_mode)
        command("+999 更早账期")

        Clock.current = datetime(2026, 9, 9, 1, 59, 59, tzinfo=ledger_storage.LEDGER_TZ)
        command("+100 上期入款")
        command("下发40 上期下发")
        before = command("+0")
        assert "总入款金额：100" in before
        assert "更早账期" not in before

        Clock.current = datetime(2026, 9, 9, 2, 0, tzinfo=ledger_storage.LEDGER_TZ)
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
