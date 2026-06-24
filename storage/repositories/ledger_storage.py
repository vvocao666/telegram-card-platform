from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable


MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.0001")


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def rate(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    chat_id: int
    kind: str
    amount: Decimal
    currency: str
    rate: Decimal
    fee_percent: Decimal
    net_amount: Decimal
    note: str
    operator_id: int
    operator_name: str
    source_message_id: int | None
    created_at: str
    voided_at: str | None


@dataclass(frozen=True)
class LedgerSummary:
    income: Decimal
    payout: Decimal
    fees: Decimal
    balance: Decimal
    income_usdt: Decimal
    payout_usdt: Decimal
    balance_usdt: Decimal
    count: int
    rate: Decimal
    fee_percent: Decimal


@dataclass(frozen=True)
class RecognizedCardRecord:
    id: int
    chat_id: int
    card_type: str
    card: str
    day_key: str
    source_user: str
    source_message_id: int | None
    created_at: str


@dataclass(frozen=True)
class CardCorrection:
    id: int
    chat_id: int
    card_type: str
    wrong_card: str
    correct_card: str
    source_user: str
    created_at: str


@dataclass(frozen=True)
class OcrTextCorrection:
    id: int
    chat_id: int
    card_type: str
    wrong_text: str
    correct_card: str
    source_user: str
    created_at: str


class LedgerStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if self.path.parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                rate TEXT NOT NULL DEFAULT '1.0000',
                fee_percent TEXT NOT NULL DEFAULT '0.0000',
                ledger_enabled INTEGER NOT NULL DEFAULT 1,
                recognition_enabled INTEGER NOT NULL DEFAULT 1,
                ledger_reset_hour INTEGER NOT NULL DEFAULT 0,
                owner_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS operators (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                added_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS known_users (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                is_bot INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );


            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('income', 'payout')),
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                rate TEXT NOT NULL,
                fee_percent TEXT NOT NULL,
                net_amount TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                operator_id INTEGER NOT NULL,
                operator_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                voided_at TEXT
            );

            CREATE TABLE IF NOT EXISTS recognized_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                card_type TEXT NOT NULL,
                card TEXT NOT NULL,
                day_key TEXT NOT NULL,
                source_user TEXT NOT NULL DEFAULT '',
                source_message_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, card_type, card, day_key)
            );

            CREATE TABLE IF NOT EXISTS card_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                card_type TEXT NOT NULL,
                wrong_card TEXT NOT NULL,
                correct_card TEXT NOT NULL,
                source_user TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, card_type, wrong_card)
            );

            CREATE TABLE IF NOT EXISTS ocr_text_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                card_type TEXT NOT NULL,
                wrong_text TEXT NOT NULL,
                correct_card TEXT NOT NULL,
                source_user TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, card_type, wrong_text)
            );

            CREATE TABLE IF NOT EXISTS bot_chats (
                chat_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                chat_type TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._add_column_if_missing("entries", "source_message_id", "INTEGER")
        self._add_column_if_missing("chat_settings", "ledger_enabled", "INTEGER NOT NULL DEFAULT 1")
        self._add_column_if_missing("chat_settings", "recognition_enabled", "INTEGER NOT NULL DEFAULT 1")
        self._add_column_if_missing("chat_settings", "ledger_reset_hour", "INTEGER NOT NULL DEFAULT 0")
        self._add_column_if_missing("chat_settings", "owner_id", "INTEGER")
        self._add_column_if_missing("known_users", "is_bot", "INTEGER NOT NULL DEFAULT 0")
        self.conn.commit()

    def _add_column_if_missing(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def remember_bot_chat(self, chat_id: int, title: str, chat_type: str) -> None:
        self.conn.execute(
            """
            INSERT INTO bot_chats (chat_id, title, chat_type, is_active, updated_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                chat_type = excluded.chat_type,
                is_active = 1,
                updated_at = excluded.updated_at
            """,
            (chat_id, title, chat_type, self._now()),
        )
        self.conn.commit()

    def list_active_bot_groups(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT chat_id, title, chat_type, updated_at
                FROM bot_chats
                WHERE is_active = 1 AND chat_type IN ('group', 'supergroup')
                ORDER BY title COLLATE NOCASE, updated_at DESC
                """
            )
        )

    def ensure_chat(self, chat_id: int) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO chat_settings (chat_id, rate, fee_percent, created_at)
            VALUES (?, '1.0000', '0.0000', ?)
            """,
            (chat_id, self._now()),
        )
        self.conn.commit()

    def get_settings(self, chat_id: int) -> tuple[Decimal, Decimal]:
        self.ensure_chat(chat_id)
        row = self.conn.execute("SELECT rate, fee_percent FROM chat_settings WHERE chat_id = ?", (chat_id,)).fetchone()
        return rate(row["rate"]), rate(row["fee_percent"])

    def set_rate(self, chat_id: int, value: Decimal | str) -> Decimal:
        self.ensure_chat(chat_id)
        new_rate = rate(value)
        if new_rate <= 0:
            raise ValueError("rate must be greater than 0")
        self.conn.execute("UPDATE chat_settings SET rate = ? WHERE chat_id = ?", (str(new_rate), chat_id))
        self.conn.commit()
        return new_rate

    def set_fee_percent(self, chat_id: int, value: Decimal | str) -> Decimal:
        self.ensure_chat(chat_id)
        new_fee = rate(value)
        if new_fee < 0:
            raise ValueError("fee percent cannot be negative")
        self.conn.execute("UPDATE chat_settings SET fee_percent = ? WHERE chat_id = ?", (str(new_fee), chat_id))
        self.conn.commit()
        return new_fee

    def is_ledger_enabled(self, chat_id: int) -> bool:
        self.ensure_chat(chat_id)
        row = self.conn.execute("SELECT ledger_enabled FROM chat_settings WHERE chat_id = ?", (chat_id,)).fetchone()
        return bool(row["ledger_enabled"])

    def set_ledger_enabled(self, chat_id: int, enabled: bool) -> None:
        self.ensure_chat(chat_id)
        self.conn.execute(
            "UPDATE chat_settings SET ledger_enabled = ? WHERE chat_id = ?",
            (1 if enabled else 0, chat_id),
        )
        self.conn.commit()

    def is_recognition_enabled(self, chat_id: int) -> bool:
        self.ensure_chat(chat_id)
        row = self.conn.execute("SELECT recognition_enabled FROM chat_settings WHERE chat_id = ?", (chat_id,)).fetchone()
        return bool(row["recognition_enabled"])

    def set_recognition_enabled(self, chat_id: int, enabled: bool) -> None:
        self.ensure_chat(chat_id)
        self.conn.execute(
            "UPDATE chat_settings SET recognition_enabled = ? WHERE chat_id = ?",
            (1 if enabled else 0, chat_id),
        )
        self.conn.commit()

    def get_ledger_reset_hour(self, chat_id: int) -> int:
        self.ensure_chat(chat_id)
        row = self.conn.execute("SELECT ledger_reset_hour FROM chat_settings WHERE chat_id = ?", (chat_id,)).fetchone()
        return int(row["ledger_reset_hour"])

    def set_ledger_reset_hour(self, chat_id: int, hour: int) -> int:
        self.ensure_chat(chat_id)
        if hour < 0 or hour > 23:
            raise ValueError("日切时间必须是0到23点")
        self.conn.execute(
            "UPDATE chat_settings SET ledger_reset_hour = ? WHERE chat_id = ?",
            (hour, chat_id),
        )
        self.conn.commit()
        return hour

    def get_chat_owner_id(self, chat_id: int) -> int | None:
        self.ensure_chat(chat_id)
        row = self.conn.execute("SELECT owner_id FROM chat_settings WHERE chat_id = ?", (chat_id,)).fetchone()
        return int(row["owner_id"]) if row and row["owner_id"] is not None else None

    def set_chat_owner(self, chat_id: int, owner_id: int, replace: bool = False) -> None:
        self.ensure_chat(chat_id)
        if replace:
            self.conn.execute("UPDATE chat_settings SET owner_id = ? WHERE chat_id = ?", (owner_id, chat_id))
        else:
            self.conn.execute(
                "UPDATE chat_settings SET owner_id = COALESCE(owner_id, ?) WHERE chat_id = ?",
                (owner_id, chat_id),
            )
        self.conn.commit()

    def add_operator(self, chat_id: int, user_id: int, username: str, display_name: str, added_by: int) -> None:
        self.ensure_chat(chat_id)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO operators (chat_id, user_id, username, display_name, added_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, username, display_name, added_by, self._now()),
        )
        self.conn.commit()

    def remove_operator(self, chat_id: int, user_id: int) -> bool:
        cursor = self.conn.execute("DELETE FROM operators WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def remember_user(self, chat_id: int, user_id: int, username: str, display_name: str, is_bot: bool = False) -> None:
        self.conn.execute(
            """
            INSERT INTO known_users (chat_id, user_id, username, display_name, is_bot, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                is_bot = excluded.is_bot,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, username.lstrip("@"), display_name, 1 if is_bot else 0, self._now()),
        )
        self.conn.commit()

    def find_known_user_by_username(self, chat_id: int, username: str) -> sqlite3.Row | None:
        username = username.lstrip("@").lower()
        return self.conn.execute(
            """
            SELECT user_id, username, display_name FROM known_users
            WHERE chat_id = ? AND lower(username) = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (chat_id, username),
        ).fetchone()

    def list_known_users_for_broadcast(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT user_id, username, display_name, is_bot, MAX(updated_at) AS updated_at
                FROM known_users
                WHERE user_id != 0 AND is_bot = 0
                GROUP BY user_id
                ORDER BY updated_at DESC
                """
            )
        )

    def list_active_known_members(self, chat_id: int, days: int = 30) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT user_id, username, display_name, is_bot, updated_at
                FROM known_users
                WHERE chat_id = ?
                  AND user_id != 0
                  AND is_bot = 0
                  AND updated_at >= datetime('now', ?)
                ORDER BY updated_at DESC
                """,
                (chat_id, f"-{days} days"),
            )
        )

    def count_active_known_members(self, chat_id: int, days: int | None = None) -> int:
        if days is None:
            row = self.conn.execute(
                "SELECT COUNT(*) AS total FROM known_users WHERE chat_id = ? AND user_id != 0 AND is_bot = 0",
                (chat_id,),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM known_users
                WHERE chat_id = ?
                  AND user_id != 0
                  AND is_bot = 0
                  AND updated_at >= datetime('now', ?)
                """,
                (chat_id, f"-{days} days"),
            ).fetchone()
        return int(row["total"] if row else 0)

    def is_operator(self, chat_id: int, user_id: int, owner_ids: Iterable[int]) -> bool:
        if user_id in set(owner_ids):
            return True
        row = self.conn.execute(
            "SELECT 1 FROM operators WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        return row is not None

    def list_operators(self, chat_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT user_id, username, display_name FROM operators WHERE chat_id = ? ORDER BY created_at",
                (chat_id,),
            )
        )

    def add_entry(
        self,
        chat_id: int,
        kind: str,
        amount: Decimal | str,
        currency: str,
        note: str,
        operator_id: int,
        operator_name: str,
        source_message_id: int | None = None,
    ) -> LedgerEntry:
        if kind not in {"income", "payout"}:
            raise ValueError("kind must be income or payout")
        amount_value = money(amount)
        if amount_value <= 0:
            raise ValueError("amount must be greater than 0")

        current_rate, fee_percent = self.get_settings(chat_id)
        converted = money(amount_value / current_rate)
        fee_amount = money(converted * fee_percent / Decimal("100"))
        net = converted - fee_amount if kind == "income" else amount_value
        now = self._now()
        cursor = self.conn.execute(
            """
            INSERT INTO entries (
                chat_id, kind, amount, currency, rate, fee_percent, net_amount, note,
                operator_id, operator_name, created_at, source_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                kind,
                str(amount_value),
                currency.upper(),
                str(current_rate),
                str(fee_percent),
                str(money(net)),
                note,
                operator_id,
                operator_name,
                now,
                source_message_id,
            ),
        )
        self.conn.commit()
        return self.get_entry(int(cursor.lastrowid))

    def get_entry(self, entry_id: int) -> LedgerEntry:
        row = self.conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise KeyError(entry_id)
        return self._entry_from_row(row)

    def entries(
        self,
        chat_id: int,
        limit: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> list[LedgerEntry]:
        conditions = ["chat_id = ?", "voided_at IS NULL"]
        params: list[object] = [chat_id]
        if start_at is not None:
            conditions.append("created_at >= ?")
            params.append(start_at)
        if end_at is not None:
            conditions.append("created_at < ?")
            params.append(end_at)
        sql = f"""
            SELECT * FROM entries
            WHERE {" AND ".join(conditions)}
            ORDER BY id ASC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def recent_entries(self, chat_id: int, limit: int = 10) -> list[LedgerEntry]:
        rows = self.conn.execute(
            """
            SELECT * FROM entries
            WHERE chat_id = ? AND voided_at IS NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def void_last_entry(self, chat_id: int) -> LedgerEntry | None:
        row = self.conn.execute(
            """
            SELECT * FROM entries
            WHERE chat_id = ? AND voided_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        self.conn.execute("UPDATE entries SET voided_at = ? WHERE id = ?", (self._now(), row["id"]))
        self.conn.commit()
        return self.get_entry(row["id"])

    def void_entry(self, chat_id: int, entry_id: int) -> LedgerEntry | None:
        row = self.conn.execute(
            """
            SELECT * FROM entries
            WHERE chat_id = ? AND id = ? AND voided_at IS NULL
            """,
            (chat_id, entry_id),
        ).fetchone()
        if row is None:
            return None
        self.conn.execute("UPDATE entries SET voided_at = ? WHERE id = ?", (self._now(), entry_id))
        self.conn.commit()
        return self.get_entry(entry_id)

    def entry_id_for_number(self, chat_id: int, number: int) -> int | None:
        if number <= 0:
            return None
        row = self.conn.execute(
            """
            SELECT id FROM entries
            WHERE chat_id = ? AND voided_at IS NULL
            ORDER BY id ASC
            LIMIT 1 OFFSET ?
            """,
            (chat_id, number - 1),
        ).fetchone()
        if row is None:
            return None
        return int(row["id"])

    def entry_for_source_message(self, chat_id: int, source_message_id: int) -> LedgerEntry | None:
        row = self.conn.execute(
            """
            SELECT * FROM entries
            WHERE chat_id = ? AND source_message_id = ? AND voided_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id, source_message_id),
        ).fetchone()
        if row is None:
            return None
        return self._entry_from_row(row)

    def active_entry_number(self, chat_id: int, entry_id: int) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count FROM entries
            WHERE chat_id = ? AND voided_at IS NULL AND id <= ?
            """,
            (chat_id, entry_id),
        ).fetchone()
        return int(row["count"])

    def clear_entries(self, chat_id: int) -> int:
        count_row = self.conn.execute(
            "SELECT COUNT(*) AS count FROM entries WHERE chat_id = ? AND voided_at IS NULL",
            (chat_id,),
        ).fetchone()
        cursor = self.conn.execute(
            "DELETE FROM entries WHERE chat_id = ?",
            (chat_id,),
        )
        self.conn.commit()
        return int(count_row["count"])

    def clear_entries_before(self, chat_id: int, cutoff_at: str) -> int:
        count_row = self.conn.execute(
            "SELECT COUNT(*) AS count FROM entries WHERE chat_id = ? AND created_at < ?",
            (chat_id, cutoff_at),
        ).fetchone()
        self.conn.execute(
            "DELETE FROM entries WHERE chat_id = ? AND created_at < ?",
            (chat_id, cutoff_at),
        )
        self.conn.commit()
        return int(count_row["count"])

    def clear_all_entries(self) -> int:
        cursor = self.conn.execute("DELETE FROM entries")
        self.conn.commit()
        return cursor.rowcount

    def record_recognized_card(
        self,
        chat_id: int,
        card_type: str,
        card: str,
        day_key: str,
        source_user: str,
        source_message_id: int | None,
    ) -> RecognizedCardRecord | None:
        existing = self.conn.execute(
            """
            SELECT * FROM recognized_cards
            WHERE chat_id = ? AND card_type = ? AND card = ? AND day_key = ?
            """,
            (chat_id, card_type, card, day_key),
        ).fetchone()
        if existing is not None:
            return self._recognized_card_from_row(existing)
        try:
            self.conn.execute(
                """
                INSERT INTO recognized_cards (
                    chat_id, card_type, card, day_key, source_user, source_message_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, card_type, card, day_key, source_user, source_message_id, self._now()),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            row = self.conn.execute(
                """
                SELECT * FROM recognized_cards
                WHERE chat_id = ? AND card_type = ? AND card = ? AND day_key = ?
                """,
                (chat_id, card_type, card, day_key),
            ).fetchone()
            return self._recognized_card_from_row(row) if row is not None else None
        return None

    def clear_recognized_cards_before(self, day_key: str) -> int:
        cursor = self.conn.execute("DELETE FROM recognized_cards WHERE day_key < ?", (day_key,))
        self.conn.commit()
        return cursor.rowcount

    def set_card_correction(
        self,
        chat_id: int,
        card_type: str,
        wrong_card: str,
        correct_card: str,
        source_user: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO card_corrections (
                chat_id, card_type, wrong_card, correct_card, source_user, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, card_type, wrong_card) DO UPDATE SET
                correct_card = excluded.correct_card,
                source_user = excluded.source_user,
                created_at = excluded.created_at
            """,
            (chat_id, card_type, wrong_card, correct_card, source_user, self._now()),
        )
        self.conn.commit()

    def get_card_correction(self, chat_id: int, card_type: str, wrong_card: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT correct_card FROM card_corrections
            WHERE card_type = ? AND wrong_card = ?
            ORDER BY CASE WHEN chat_id = ? THEN 0 ELSE 1 END, created_at DESC
            LIMIT 1
            """,
            (card_type, wrong_card, chat_id),
        ).fetchone()
        return str(row["correct_card"]) if row is not None else None

    def list_card_corrections(self, chat_id: int) -> list[CardCorrection]:
        rows = self.conn.execute(
            """
            SELECT * FROM card_corrections
            ORDER BY CASE WHEN chat_id = ? THEN 0 ELSE 1 END, created_at DESC
            """,
            (chat_id,),
        ).fetchall()
        return [self._card_correction_from_row(row) for row in rows]

    def set_ocr_text_correction(
        self,
        chat_id: int,
        card_type: str,
        wrong_text: str,
        correct_card: str,
        source_user: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO ocr_text_corrections (
                chat_id, card_type, wrong_text, correct_card, source_user, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, card_type, wrong_text) DO UPDATE SET
                correct_card = excluded.correct_card,
                source_user = excluded.source_user,
                created_at = excluded.created_at
            """,
            (chat_id, card_type, wrong_text, correct_card, source_user, self._now()),
        )
        self.conn.commit()

    def list_ocr_text_corrections(self, chat_id: int) -> list[OcrTextCorrection]:
        rows = self.conn.execute(
            """
            SELECT * FROM ocr_text_corrections
            ORDER BY CASE WHEN chat_id = ? THEN 0 ELSE 1 END, created_at DESC
            """,
            (chat_id,),
        ).fetchall()
        return [self._ocr_text_correction_from_row(row) for row in rows]

    def summary(self, chat_id: int) -> LedgerSummary:
        current_rate, fee_percent = self.get_settings(chat_id)
        rows = self.conn.execute(
            "SELECT kind, net_amount, amount, rate, fee_percent FROM entries WHERE chat_id = ? AND voided_at IS NULL",
            (chat_id,),
        ).fetchall()
        income = Decimal("0")
        income_usdt = Decimal("0")
        payout_usdt = Decimal("0")
        fees = Decimal("0")
        for row in rows:
            converted = money(Decimal(row["amount"]) / Decimal(row["rate"]))
            fee_amount = money(converted * Decimal(row["fee_percent"]) / Decimal("100"))
            if row["kind"] == "income":
                income += Decimal(row["amount"])
                income_usdt += Decimal(row["net_amount"])
                fees += fee_amount
            else:
                payout_usdt += Decimal(row["net_amount"])
        return LedgerSummary(
            income=money(income),
            payout=money(payout_usdt),
            fees=money(fees),
            balance=money(max(income_usdt - payout_usdt, Decimal("0"))),
            income_usdt=money(income_usdt),
            payout_usdt=money(payout_usdt),
            balance_usdt=money(max(income_usdt - payout_usdt, Decimal("0"))),
            count=len(rows),
            rate=current_rate,
            fee_percent=fee_percent,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")

    @staticmethod
    def _entry_from_row(row: sqlite3.Row) -> LedgerEntry:
        return LedgerEntry(
            id=row["id"],
            chat_id=row["chat_id"],
            kind=row["kind"],
            amount=money(row["amount"]),
            currency=row["currency"],
            rate=rate(row["rate"]),
            fee_percent=rate(row["fee_percent"]),
            net_amount=money(row["net_amount"]),
            note=row["note"],
            operator_id=row["operator_id"],
            operator_name=row["operator_name"],
            source_message_id=row["source_message_id"],
            created_at=row["created_at"],
            voided_at=row["voided_at"],
        )

    @staticmethod
    def _recognized_card_from_row(row: sqlite3.Row) -> RecognizedCardRecord:
        return RecognizedCardRecord(
            id=row["id"],
            chat_id=row["chat_id"],
            card_type=row["card_type"],
            card=row["card"],
            day_key=row["day_key"],
            source_user=row["source_user"],
            source_message_id=row["source_message_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _card_correction_from_row(row: sqlite3.Row) -> CardCorrection:
        return CardCorrection(
            id=row["id"],
            chat_id=row["chat_id"],
            card_type=row["card_type"],
            wrong_card=row["wrong_card"],
            correct_card=row["correct_card"],
            source_user=row["source_user"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _ocr_text_correction_from_row(row: sqlite3.Row) -> OcrTextCorrection:
        return OcrTextCorrection(
            id=row["id"],
            chat_id=row["chat_id"],
            card_type=row["card_type"],
            wrong_text=row["wrong_text"],
            correct_card=row["correct_card"],
            source_user=row["source_user"],
            created_at=row["created_at"],
        )
