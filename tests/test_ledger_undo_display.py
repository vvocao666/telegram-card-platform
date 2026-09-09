import pytest

from services.ledger import ledger_commands
from storage.repositories.ledger_storage import LedgerStore


@pytest.mark.parametrize("view_mode", ["compact", "detailed"])
@pytest.mark.parametrize("command", ["+100", "下发100"])
def test_undo_original_message_only_repeats_restored_bill(tmp_path, view_mode, command):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    actor = ledger_commands.Actor(7, "boss", "Boss")
    try:
        store.set_ledger_view_mode(-1001, view_mode)
        for index, amount in enumerate((100, 200, 300, 400, 100), start=1):
            ledger_commands.handle_text(store, -1001, actor, f"+{amount}", {7}, message_id=index)
        before = ledger_commands.format_bill(store, -1001)
        ledger_commands.handle_text(store, -1001, actor, command, {7}, message_id=6)

        result = ledger_commands.handle_text(
            store, -1001, actor, "撤销", {7}, reply_text=command, reply_message_id=6,
        )

        assert result.changed is True
        assert result.text == before
        assert result.text.startswith("已入款(5笔)")
        assert "已撤销" not in result.text
        assert "总入款金额：1100" in result.text.splitlines()
        assert len(store.entries(-1001)) == 5
        assert store.entry_for_source_message(-1001, 6) is None
    finally:
        store.close()
