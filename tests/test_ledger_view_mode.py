from __future__ import annotations

import asyncio
from types import SimpleNamespace

import services.runtime as runtime
from services.ledger import ledger_commands
from storage.repositories.ledger_storage import LedgerStore


def test_compact_mode_hides_recent_entries_and_persists(tmp_path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    store = LedgerStore(db_path)
    try:
        store.add_entry(-1001, "income", "100", "USDT", "一手核销（PUBG/PSN）", 7, "Boss", 1)
        assert "最近流水：" in ledger_commands.format_bill(store, -1001)

        store.set_ledger_view_mode(-1001, "compact")
        compact = ledger_commands.format_bill(store, -1001)
        assert "已入款(1笔)" in compact
        assert "总入款金额：100" in compact
        assert "最近流水：" not in compact
    finally:
        store.close()

    reopened = LedgerStore(db_path)
    try:
        assert reopened.get_ledger_view_mode(-1001) == "compact"
    finally:
        reopened.close()


def test_compact_mode_hides_operator_but_keeps_reply_user_and_manual_note(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    boss = ledger_commands.Actor(7, "boss", "Boss")
    customer = ledger_commands.Actor(8, "customer", "Customer")
    try:
        ledger_commands.handle_text(store, -1001, boss, "设置汇率10", {7})
        ledger_commands.handle_text(store, -1001, boss, "+100", {7}, message_id=1)
        ledger_commands.handle_text(
            store,
            -1001,
            boss,
            "+25",
            {7},
            reply_user=customer,
            message_id=2,
        )
        ledger_commands.handle_text(store, -1001, boss, "+12.5 单独备注", {7}, message_id=3)
        ledger_commands.handle_text(store, -1001, boss, "下发50", {7}, message_id=4)

        detailed = ledger_commands.format_bill(store, -1001)
        detailed_top = detailed.split("\n\n最近流水：", 1)[0]
        assert detailed_top.count(" Boss") == 2
        assert " Customer" in detailed_top
        assert " 单独备注" in detailed_top

        store.set_ledger_view_mode(-1001, "compact")
        compact = ledger_commands.format_bill(store, -1001)
        assert " Boss" not in compact
        assert "25/10=2.5U Customer" in compact
        assert "12.5/10=1.25U 单独备注" in compact
        assert '<a href="https://t.me/">-50U</a> Boss' not in compact
    finally:
        store.close()


def test_ledger_keyboard_shows_one_current_mode_button() -> None:
    keyboard = runtime.ledger_keyboard("today", "detailed").inline_keyboard

    assert [[button.text for button in row] for row in keyboard] == [
        ["今日账单", "昨日账单"],
        ["详细模式"],
    ]
    assert keyboard[1][0].callback_data == "ledger:view:compact:today"

    compact_keyboard = runtime.ledger_keyboard("today", "compact").inline_keyboard
    assert [button.text for button in compact_keyboard[1]] == ["简洁模式"]
    assert compact_keyboard[1][0].callback_data == "ledger:view:detailed:today"


def test_instruction_text_aliases_open_help(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    actor = ledger_commands.Actor(7, "boss", "Boss")
    try:
        result = ledger_commands.handle_text(store, -1001, actor, "/使用说明", {7})
        assert result is not None
        assert result.text == ledger_commands.HELP_TEXT
        assert ledger_commands.handle_text(store, -1001, actor, "使用说明", {7}) is None
    finally:
        store.close()


def test_bill_rate_and_fee_share_one_line_with_exact_fixed_rate(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        store.set_fee_percent(-1001, "5")
        for mode in ("compact", "detailed"):
            store.set_ledger_view_mode(-1001, mode)
            for value, label in (("1", "1"), ("6.8", "6.8"), ("6.8754", "6.8754")):
                store.set_rate(-1001, value)
                for scope in ("today", "yesterday", "full"):
                    bill = ledger_commands.format_bill(store, -1001, scope=scope)
                    assert f"汇率：{label} | 费率：5%" in bill.splitlines()
                    assert "\n费率：" not in bill
    finally:
        store.close()


def test_bill_amounts_trim_trailing_zeros_without_changing_entries(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        store.add_entry(-1001, "income", "95.50", "USDT", "", 7, "Boss", 1)
        store.add_entry(-1001, "payout", "90", "USDT", "", 7, "Boss", 2)
        original = store.entries(-1001)
        for mode in ("compact", "detailed"):
            store.set_ledger_view_mode(-1001, mode)
            bill = ledger_commands.format_bill(store, -1001)
            assert "总入款金额：95.5" in bill.splitlines()
            assert "应下发：95.5 | 95.5U" in bill.splitlines()
            assert "已下发：90U" in bill.splitlines()
            assert ">5.5U</a>" in bill
            assert ".00" not in bill
            assert "95.50" not in bill
        assert store.entries(-1001) == original
    finally:
        store.close()


def test_realtime_rate_label_persists_and_manual_rate_clears_it(tmp_path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    store = LedgerStore(db_path)
    try:
        store.set_rate(-1001, "7.2", is_realtime=True)
        entry = store.add_entry(-1001, "income", "720", "USDT", "", 7, "Boss", 1)
    finally:
        store.close()

    store = LedgerStore(db_path)
    try:
        assert "汇率：7.20 | 费率：0%" in ledger_commands.format_bill(store, -1001)
        actor = ledger_commands.Actor(7, "boss", "Boss")
        ledger_commands.handle_text(store, -1001, actor, "设置汇率1", {7})
        bill = ledger_commands.format_bill(store, -1001)
        assert "汇率：1 | 费率：0%" in bill
        assert "实时汇率" not in bill
        assert store.entries(-1001)[0] == entry
        assert "应下发：720 | 100U" in bill
    finally:
        store.close()


class FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = SimpleNamespace(chat_id=-1001)
        self.from_user = SimpleNamespace(id=7, username="boss", first_name="Boss", last_name="")
        self.answered = False
        self.edits: list[tuple[str, dict]] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edits.append((text, kwargs))


def test_explicit_bills_show_all_income_and_payout_rows(monkeypatch, tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    actor = ledger_commands.Actor(7, "boss", "Boss")
    monkeypatch.setattr(runtime, "ledger_store", store)
    try:
        older = store.add_entry(-1001, "income", "9999", "USDT", "旧账期", 7, "Boss", 1)
        store.conn.execute(
            "UPDATE entries SET accounting_date=? WHERE id=?",
            (store.previous_accounting_date(-1001), older.id),
        )
        store.conn.commit()
        for index in range(1, 5):
            store.add_entry(-1001, "income", str(index * 100), "USDT", f"入款{index}", 7, "Boss", index + 1)
            store.add_entry(-1001, "payout", str(index * 10), "USDT", f"下发{index}", 7, "Boss", index + 5)

        for mode in ("compact", "detailed"):
            store.set_ledger_view_mode(-1001, mode)
            for text in ("今日账单", "+0", "完整账单"):
                bill = ledger_commands.handle_text(store, -1001, actor, text, {7}).text
                top = bill.split("\n\n最近流水：", 1)[0]
                assert "已入款(4笔)" in top
                assert "已下发(4笔)" in top
                assert "总入款金额：1000" in top.splitlines()
                assert "已下发：100U" in top.splitlines()
                for index in range(1, 5):
                    assert top.count(f"入款{index}") == 1
                    assert top.count(f"下发{index}") == 1
                assert "旧账期" not in bill

        store.set_ledger_view_mode(-1001, "detailed")
        query = FakeQuery("ledger:view:compact:full")
        asyncio.run(runtime.handle_ledger_callback(SimpleNamespace(callback_query=query), object()))
        assert "入款1" in query.edits[-1][0]
        assert "下发1" in query.edits[-1][0]

        store.conn.execute(
            "UPDATE entries SET accounting_date=? WHERE id<>?",
            (store.previous_accounting_date(-1001), older.id),
        )
        store.conn.commit()
        yesterday = ledger_commands.handle_text(store, -1001, actor, "昨日账单", {7}).text
        for index in range(1, 5):
            assert f"入款{index}" in yesterday
            assert f"下发{index}" in yesterday
    finally:
        store.close()


def test_long_full_bill_and_mode_toggle_send_every_row_in_chunks(monkeypatch, tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(runtime, "ledger_store", store)
    sent = []

    async def reply_text(text, **kwargs):
        assert len(text) <= 4096
        sent.append((text, kwargs))

    message = SimpleNamespace(chat_id=-1001, reply_text=reply_text)
    try:
        store.set_ledger_view_mode(-1001, "compact")
        for index in range(180):
            store.add_entry(-1001, "income", "1", "USDT", f"row-{index:03}", 7, "Boss", index + 1)
        bill = ledger_commands.format_bill(store, -1001, scope="full", show_all_records=True)
        asyncio.run(runtime.reply_ledger(message, bill))
        assert len(sent) > 1
        assert "\n".join(text for text, _ in sent) == bill
        assert sent[0][1]["reply_markup"] is not None
        assert all(kwargs["reply_markup"] is None for _, kwargs in sent[1:])

        sent.clear()
        query = FakeQuery("ledger:view:detailed:full")
        query.message = message
        asyncio.run(runtime.handle_ledger_callback(SimpleNamespace(callback_query=query), object()))
        assert len(query.edits[0][0]) <= 4096
        assert sent
        combined = "\n".join([query.edits[0][0], *(text for text, _ in sent)])
        expected = ledger_commands.format_bill(store, -1001, scope="full", show_all_records=True)
        assert combined == expected
        for index in range(180):
            assert f"row-{index:03}" in combined
    finally:
        store.close()


def test_ledger_view_button_toggles_message_and_saved_mode(monkeypatch, tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(runtime, "ledger_store", store)
    store.add_entry(-1001, "income", "100", "USDT", "", 7, "Boss", 1)
    try:
        compact_query = FakeQuery("ledger:view:compact:today")
        asyncio.run(runtime.handle_ledger_callback(SimpleNamespace(callback_query=compact_query), object()))

        assert compact_query.answered is True
        assert store.get_ledger_view_mode(-1001) == "compact"
        assert "最近流水：" not in compact_query.edits[-1][0]
        compact_button = compact_query.edits[-1][1]["reply_markup"].inline_keyboard[-1][0]
        assert compact_button.text == "简洁模式"
        assert compact_button.callback_data == "ledger:view:detailed:today"

        unchanged_query = FakeQuery("ledger:view:compact:today")
        asyncio.run(runtime.handle_ledger_callback(SimpleNamespace(callback_query=unchanged_query), object()))
        assert unchanged_query.answered is True
        assert unchanged_query.edits == []

        detailed_query = FakeQuery("ledger:view:detailed:today")
        asyncio.run(runtime.handle_ledger_callback(SimpleNamespace(callback_query=detailed_query), object()))

        assert store.get_ledger_view_mode(-1001) == "detailed"
        assert "最近流水：" in detailed_query.edits[-1][0]
        detailed_button = detailed_query.edits[-1][1]["reply_markup"].inline_keyboard[-1][0]
        assert detailed_button.text == "详细模式"
        assert detailed_button.callback_data == "ledger:view:compact:today"
    finally:
        store.close()
