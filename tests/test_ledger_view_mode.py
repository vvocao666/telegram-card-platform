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
        assert compact_button.text == "详细模式"
        assert compact_button.callback_data == "ledger:view:detailed:today"

        detailed_query = FakeQuery("ledger:view:detailed:today")
        asyncio.run(runtime.handle_ledger_callback(SimpleNamespace(callback_query=detailed_query), object()))

        assert store.get_ledger_view_mode(-1001) == "detailed"
        assert "最近流水：" in detailed_query.edits[-1][0]
        detailed_button = detailed_query.edits[-1][1]["reply_markup"].inline_keyboard[-1][0]
        assert detailed_button.text == "简洁模式"
    finally:
        store.close()
