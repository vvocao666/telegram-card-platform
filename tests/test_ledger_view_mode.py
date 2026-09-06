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
        assert "总入款金额：100.00" in compact
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
        assert "25/10=2.50U Customer" in compact
        assert "12.50/10=1.25U 单独备注" in compact
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
