from decimal import Decimal
import asyncio
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
        assert "✅ 当前群费率已设置为：10.00%" in result.text
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
        assert "手续费：" not in bill.text
        assert "费率：10.00%\n\n应下发：" in bill.text
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
        assert "手续费：" not in bill.text
        assert "应下发：45000.00 | 6617.65U" in bill.text
    finally:
        store.close()


def test_payout_returns_compact_transfer_confirmation(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()

        payout = ledger_commands.handle_text(store, -1001, boss, "下发1000", {12345}, message_id=1)
        income = ledger_commands.handle_text(store, -1001, boss, "+100", {12345}, message_id=2)
        private_payout = ledger_commands.handle_text(store, 12345, boss, "下发50", {12345}, message_id=3)
        shorthand_adjustment = ledger_commands.handle_text(store, -1001, boss, "-500", {12345}, message_id=4)
        negative_named_payout = ledger_commands.handle_text(
            store, -1001, boss, "下发-200", {12345}, message_id=5
        )
        payout_alias = ledger_commands.handle_text(store, -1001, boss, "出款300", {12345}, message_id=6)
        slash_alias = ledger_commands.handle_text(store, -1001, boss, "/out300", {12345}, message_id=7)
        payout_slash_alias = ledger_commands.handle_text(store, -1001, boss, "/payout300", {12345}, message_id=8)
        lower_alias = ledger_commands.handle_text(store, -1001, boss, "下分300", {12345}, message_id=9)

        assert payout is not None
        assert payout.follow_up_text == '💰<b><a href="https://t.me/">【 1000 UU 】</a></b>  已转✅，请您查收。'
        assert income is not None
        assert income.follow_up_text is None
        assert private_payout is not None
        assert private_payout.follow_up_text is None
        assert shorthand_adjustment is not None
        assert shorthand_adjustment.follow_up_text is None
        assert negative_named_payout is not None
        assert negative_named_payout.follow_up_text is None
        assert payout_alias is None
        assert slash_alias is None
        assert payout_slash_alias is None
        assert lower_alias is None
        entries = store.entries(-1001)
        assert [(entry.kind, entry.amount) for entry in entries] == [
            ("payout", Decimal("1000.00")),
            ("income", Decimal("100.00")),
            ("income", Decimal("-500.00")),
            ("payout", Decimal("-200.00")),
        ]
    finally:
        store.close()


def test_negative_amount_adjusts_income_without_creating_a_payout(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()

        ledger_commands.handle_text(store, -1001, boss, "+1000", {12345}, message_id=1)
        adjustment = ledger_commands.handle_text(store, -1001, boss, "-100", {12345}, message_id=2)

        assert adjustment is not None
        assert "总入款金额：900.00" in adjustment.text
        assert "应下发：900.00 | 900.00U" in adjustment.text
        assert "已入款(2笔)" in adjustment.text
        assert "减分(1笔)" not in adjustment.text
        assert "已下发(0笔)" in adjustment.text
        assert "已下发：0.00U" in adjustment.text
        assert [(entry.kind, entry.amount) for entry in store.entries(-1001)] == [
            ("income", Decimal("1000.00")),
            ("income", Decimal("-100.00")),
        ]
    finally:
        store.close()


def test_group_lines_use_compact_amounts_and_command_sender_attribution(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()
        customer = actor(67890)
        ledger_commands.handle_text(store, -1001, boss, "设置汇率10", {12345})
        ledger_commands.handle_text(store, -1001, boss, "+100", {12345}, message_id=1)
        ledger_commands.handle_text(
            store,
            -1001,
            boss,
            "+25",
            {12345},
            reply_user=customer,
            message_id=2,
        )
        ledger_commands.handle_text(store, -1001, boss, "+12.5 雄霸小火箭", {12345}, message_id=3)
        ledger_commands.handle_text(store, -1001, boss, "下发50", {12345}, message_id=4)

        entries = store.entries(-1001)
        income_lines = ledger_commands._format_group_lines(
            [(index, entry) for index, entry in enumerate(entries, start=1) if entry.kind == "income"]
        )
        payout_lines = ledger_commands._format_group_lines(
            [(index, entry) for index, entry in enumerate(entries, start=1) if entry.kind == "payout"]
        )

        assert income_lines[0].endswith("100/10=10U User 12345")
        assert income_lines[1].endswith("25/10=2.50U User 67890")
        assert income_lines[2].endswith("12.50/10=1.25U 雄霸小火箭")
        assert payout_lines[0].endswith(
            '<a href="https://t.me/">-50U</a> User 12345'
        )

        bill = ledger_commands.format_bill(store, -1001)
        recent = bill.split("最近流水：", 1)[1]
        assert " U User 67890" not in recent
        assert " U User 12345" not in recent
        assert " U 雄霸小火箭" not in recent
        assert "\n         User 67890" in recent
        assert "\n         User 12345" in recent
        assert "\n         雄霸小火箭" in recent
    finally:
        store.close()


def test_payout_sign_is_preserved_in_paid_and_unpaid_totals(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()

        positive = ledger_commands.handle_text(store, -1001, boss, "下发100", {12345}, message_id=1)
        assert positive is not None
        assert "应下发：0.00 | 0.00U" in positive.text
        assert "已下发：100.00U" in positive.text
        assert '未下发：【<a href="https://t.me/">-100.00U</a>】' in positive.text

        store.clear_entries(-1001)
        negative = ledger_commands.handle_text(store, -1001, boss, "下发-200", {12345}, message_id=2)
        assert negative is not None
        assert "应下发：0.00 | 0.00U" in negative.text
        assert "已下发：-200.00U" in negative.text
        assert '未下发：【<a href="https://t.me/">200.00U</a>】' in negative.text
        assert "--200" not in negative.text

        entry = store.entries(-1001)[0]
        assert entry.amount == Decimal("-200.00")
        assert entry.net_amount == Decimal("-200.00")
    finally:
        store.close()


def test_payout_confirmation_still_sends_when_ledger_is_disabled_without_writing_entry(tmp_path):
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    try:
        boss = actor()
        store.set_ledger_enabled(-1001, False)

        named_payout = ledger_commands.handle_text(store, -1001, boss, "下发1000", {12345}, message_id=1)
        signed_payout = ledger_commands.handle_text(store, -1001, boss, "-500", {12345}, message_id=2)
        income = ledger_commands.handle_text(store, -1001, boss, "+100", {12345}, message_id=3)

        assert named_payout is not None
        assert named_payout.text == ""
        assert named_payout.follow_up_text == (
            '💰<b><a href="https://t.me/">【 1000 UU 】</a></b>  已转✅，请您查收。'
        )
        assert signed_payout is None
        assert income is None
        assert store.entries(-1001) == []
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
        assert "手续费：" not in before.text
        assert "应下发：900.00 | 90.00U" in before.text
        assert "手续费：" not in after.text
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
        bill = ledger_commands.handle_text(store, -1001, actor(), "完整账单", {12345})

        assert entry.fee_percent == Decimal("0.0000")
        assert entry.fee_amount == Decimal("0.00")
        assert entry.payable_amount == Decimal("50000.00")
        assert entry.payable_usdt == Decimal("5000.00")
        assert bill is not None
        assert "手续费：" not in bill.text
        assert "应下发：50000.00 | 5000.00U" in bill.text
    finally:
        store.close()


def test_cloud_deploy_remote_ocr_default_is_disabled():
    from pathlib import Path

    env_example = Path(".env.example").read_text(encoding="utf-8")
    assert "REMOTE_OCR_ENABLED=false" in env_example


class FakeUser:
    id = 12345
    username = "boss"
    first_name = "Boss"
    last_name = ""
    is_bot = False


class FakeChat:
    id = -1001
    type = "supergroup"
    title = "Test Group"


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.caption = None
        self.message_id = 100
        self.reply_to_message = None
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, text: str):
        self.message = FakeMessage(text)
        self.effective_chat = FakeChat()
        self.effective_user = FakeUser()


def test_set_realtime_rate_updates_current_group_only(monkeypatch, tmp_path):
    import bot

    store = LedgerStore(tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(bot, "ledger_store", store)
    store.set_chat_owner(-1001, 12345)

    async def fake_fetch():
        return [Decimal("7.23"), Decimal("7.24")], "OKX C2C卖单"

    monkeypatch.setattr(bot, "fetch_okx_usdt_cny_prices", fake_fetch)
    try:
        update = FakeUpdate("设置实时汇率")
        handled = asyncio.run(bot.handle_ledger_text(update, object(), allow_trc20=False))

        assert handled is True
        assert store.get_settings(-1001)[0] == Decimal("7.2300")
        assert "✅ 当前群实时汇率已更新" in update.message.replies[-1]
        assert "汇率：7.23" in update.message.replies[-1]
        assert "来源：欧意 USDT/CNY 最新 1 档" in update.message.replies[-1]
    finally:
        store.close()


def test_price_command_does_not_modify_group_rate(monkeypatch, tmp_path):
    import bot

    for command in ("币价", "bj", "Z0"):
        store = LedgerStore(tmp_path / f"{command}.sqlite3")
        monkeypatch.setattr(bot, "ledger_store", store)
        store.set_rate(-1001, "6.66")

        async def fake_fetch():
            return [Decimal("7.23"), Decimal("7.24"), Decimal("7.25"), Decimal("7.26"), Decimal("7.27")], "OKX C2C卖单"

        monkeypatch.setattr(bot, "fetch_okx_usdt_cny_prices", fake_fetch)
        try:
            update = FakeUpdate(command)
            handled = asyncio.run(bot.handle_ledger_text(update, object(), allow_trc20=False))

            assert handled is True
            assert store.get_settings(-1001)[0] == Decimal("6.6600")
            assert "欧意USDT/CNY 最新5档" in update.message.replies[-1]
            assert "1. 7.23" in update.message.replies[-1]
        finally:
            store.close()


def test_set_realtime_rate_failure_keeps_old_rate(monkeypatch, tmp_path):
    import bot

    store = LedgerStore(tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(bot, "ledger_store", store)
    store.set_chat_owner(-1001, 12345)
    store.set_rate(-1001, "6.66")

    async def fake_fetch():
        raise RuntimeError("network down")

    monkeypatch.setattr(bot, "fetch_okx_usdt_cny_prices", fake_fetch)
    try:
        update = FakeUpdate("设置实时汇率")
        handled = asyncio.run(bot.handle_ledger_text(update, object(), allow_trc20=False))

        assert handled is True
        assert store.get_settings(-1001)[0] == Decimal("6.6600")
        assert "❌ 获取欧意实时汇率失败" in update.message.replies[-1]
        assert "6.66" in update.message.replies[-1]
    finally:
        store.close()


def test_price_command_failure_keeps_old_rate(monkeypatch, tmp_path):
    import bot

    store = LedgerStore(tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(bot, "ledger_store", store)
    store.set_chat_owner(-1001, 12345)
    store.set_rate(-1001, "6.66")

    async def fake_fetch():
        raise RuntimeError("network down")

    monkeypatch.setattr(bot, "fetch_okx_usdt_cny_prices", fake_fetch)
    try:
        update = FakeUpdate("币价")
        handled = asyncio.run(bot.handle_ledger_text(update, object(), allow_trc20=False))

        assert handled is True
        assert store.get_settings(-1001)[0] == Decimal("6.6600")
        assert "币价获取失败" in update.message.replies[-1]
    finally:
        store.close()
