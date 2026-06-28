from decimal import Decimal
import sqlite3

from services.ledger import ledger_commands
from storage.repositories.ledger_storage import LedgerStore


def actor(user_id: int = 12345) -> ledger_commands.Actor:
    return ledger_commands.Actor(user_id=user_id, username=f"user{user_id}", display_name=f"User {user_id}")


def test_set_fee_rate_ten_success(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        result = ledger_commands.handle_text(store, -1001, actor(), "设置费率10", {12345})

        assert result is not None
        assert "✅ 已设置本群费率：10.00%" in result.text
        assert "当前汇率：1.00" in result.text
        assert "当前费率：10.00%" in result.text
        assert store.get_settings(-1001)[1] == Decimal("10.0000")
    finally:
        store.close()


def test_set_fee_rate_zero_success(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        result = ledger_commands.handle_text(store, -1001, actor(), "/set_fee 0", {12345})

        assert result is not None
        assert "0.00%" in result.text
        assert store.get_settings(-1001)[1] == Decimal("0.0000")
    finally:
        store.close()


def test_set_fee_rate_rejects_one_hundred(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        result = ledger_commands.handle_text(store, -1001, actor(), "设置费率100", {12345})

        assert result is not None
        assert "费率必须小于100" in result.text
        assert store.get_settings(-1001)[1] == Decimal("0.0000")
    finally:
        store.close()


def test_set_fee_rate_rejects_normal_user(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        result = ledger_commands.handle_text(store, -1001, actor(67890), "设置费率10", {12345})

        assert result is not None
        assert "无权限设置费率" in result.text
        assert store.get_settings(-1001)[1] == Decimal("0.0000")
    finally:
        store.close()


def test_fee_calculation_rate_ten(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()
        ledger_commands.handle_text(store, -1001, boss, "设置汇率10", {12345})
        ledger_commands.handle_text(store, -1001, boss, "设置费率10", {12345})
        ledger_commands.handle_text(store, -1001, boss, "+50000", {12345}, message_id=1)
        bill = ledger_commands.handle_text(store, -1001, boss, "账单", {12345})

        assert bill is not None
        assert "总入款金额：50000.00" in bill.text
        assert "汇率：10.00" in bill.text
        assert "费率：10.00%" in bill.text
        assert "手续费：5000.00" in bill.text
        assert "应下发：45000.00 | 4500.00U" in bill.text
    finally:
        store.close()


def test_fee_calculation_rate_six_point_eight(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()
        ledger_commands.handle_text(store, -1001, boss, "设置汇率6.8", {12345})
        ledger_commands.handle_text(store, -1001, boss, "设置费率10", {12345})
        ledger_commands.handle_text(store, -1001, boss, "+50000", {12345}, message_id=1)
        bill = ledger_commands.handle_text(store, -1001, boss, "账单", {12345})

        assert bill is not None
        assert "手续费：5000.00" in bill.text
        assert "应下发：45000.00 | 6617.65U" in bill.text
    finally:
        store.close()


def test_fee_change_only_affects_new_entries(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()
        ledger_commands.handle_text(store, -1001, boss, "设置汇率10", {12345})
        ledger_commands.handle_text(store, -1001, boss, "设置费率10", {12345})
        first = store.add_entry(-1001, "income", "1000", "USDT", "", boss.user_id, boss.label, 1)
        ledger_commands.handle_text(store, -1001, boss, "设置费率20", {12345})
        second = store.add_entry(-1001, "income", "1000", "USDT", "", boss.user_id, boss.label, 2)

        assert first.fee_percent == Decimal("10.0000")
        assert first.fee_amount == Decimal("100.00")
        assert first.payable_amount == Decimal("900.00")
        assert first.payable_usdt == Decimal("90.00")
        assert second.fee_percent == Decimal("20.0000")
        assert second.fee_amount == Decimal("200.00")
        assert second.payable_amount == Decimal("800.00")
        assert second.payable_usdt == Decimal("80.00")
    finally:
        store.close()


def test_historical_bill_does_not_recalculate_after_fee_change(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()
        ledger_commands.handle_text(store, -1001, boss, "设置汇率10", {12345})
        ledger_commands.handle_text(store, -1001, boss, "设置费率10", {12345})
        store.add_entry(-1001, "income", "1000", "USDT", "", boss.user_id, boss.label, 1)
        before = ledger_commands.handle_text(store, -1001, boss, "账单", {12345})
        ledger_commands.handle_text(store, -1001, boss, "设置费率20", {12345})
        after = ledger_commands.handle_text(store, -1001, boss, "账单", {12345})

        assert before is not None
        assert after is not None
        assert "手续费：100.00" in before.text
        assert "应下发：900.00 | 90.00U" in before.text
        assert "手续费：100.00" in after.text
        assert "应下发：900.00 | 90.00U" in after.text
    finally:
        store.close()


def test_legacy_data_migrates_with_zero_fee(tmp_path):
    db_path = tmp_path / "ledger.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE chat_settings (
            chat_id INTEGER PRIMARY KEY,
            rate TEXT NOT NULL DEFAULT '1.0000',
            ledger_enabled INTEGER NOT NULL DEFAULT 1,
            recognition_enabled INTEGER NOT NULL DEFAULT 1,
            ledger_reset_hour INTEGER NOT NULL DEFAULT 0,
            owner_id INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('income', 'payout')),
            amount TEXT NOT NULL,
            currency TEXT NOT NULL,
            rate TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            operator_id INTEGER NOT NULL,
            operator_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            voided_at TEXT
        );
        INSERT INTO chat_settings (chat_id, rate, created_at) VALUES (-1001, '10.0000', '2026-06-28T00:00:00+00:00');
        INSERT INTO entries (chat_id, kind, amount, currency, rate, note, operator_id, operator_name, created_at)
        VALUES (-1001, 'income', '50000.00', 'USDT', '10.0000', '', 12345, '@boss', '2026-06-28T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    store = LedgerStore(db_path)
    try:
        entry = store.entries(-1001)[0]
        bill = ledger_commands.handle_text(store, -1001, actor(), "账单", {12345})

        assert entry.fee_percent == Decimal("0.0000")
        assert entry.fee_amount == Decimal("0.00")
        assert entry.payable_amount == Decimal("50000.00")
        assert entry.payable_usdt == Decimal("5000.00")
        assert bill is not None
        assert "手续费：0.00" in bill.text
        assert "应下发：50000.00 | 5000.00U" in bill.text
    finally:
        store.close()


def test_cloud_deploy_remote_ocr_default_is_disabled():
    from pathlib import Path

    env_example = Path(".env.example").read_text(encoding="utf-8")
    assert "REMOTE_OCR_ENABLED=false" in env_example
