from pathlib import Path

from services.ledger import ledger_commands
from storage.repositories import ledger_storage


def test_ledger_snapshots_exist():
    assert Path("services/ledger/ledger_service.py").exists()
    assert Path("services/ledger/ledger_commands.py").exists()
    assert Path("storage/repositories/ledger_storage.py").exists()


def test_ledger_command_snapshot_contains_current_entry_point():
    text = Path("services/ledger/ledger_commands.py").read_text(encoding="utf-8")

    assert "def handle_text" in text
    assert "def format_bill" in text


def test_ledger_current_logic_still_uses_original_modules(tmp_path):
    store = ledger_storage.LedgerStore(tmp_path / "ledger.sqlite3")
    actor = ledger_commands.Actor(user_id=123, username="boss", display_name="Boss")

    try:
        result = ledger_commands.handle_text(store, -1001, actor, "+100", {123})
        assert result is not None
    finally:
        store.close()
