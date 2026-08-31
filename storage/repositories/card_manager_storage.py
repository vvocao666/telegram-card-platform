from __future__ import annotations

"""持久化 Windows 卡密管理端所需的旁路数据。

本模块不参与 OCR、群内回复或现有重复提醒；写入失败由调用方记录日志后忽略。
所有 Telegram 原始字段都保留，显示别名和人工校对字段独立存放。
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Iterable


ORDER_GAP = 1024
MANUAL_ID_BASE = -900_000_000_000_000_000


@dataclass(frozen=True)
class CardRecordInput:
    telegram_chat_id: int
    telegram_chat_title: str
    telegram_user_id: int
    telegram_user_name: str
    telegram_user_username: str
    telegram_message_id: int
    telegram_message_date: str
    media_group_id: str
    image_index: int
    card_index: int
    card_type: str
    ocr_original_card: str
    final_card: str
    denomination: str
    original_image_path: str
    telegram_file_id: str
    telegram_file_unique_id: str
    image_cached_at: str
    image_expires_at: str
    ocr_failed: bool = False


class CardManagerStore:
    """使用现有 SQLite 文件的独立表，避免改动账本与 OCR 历史表。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _normalize_denomination(denomination: str) -> str:
        """管理端允许人工使用任意非空卡种，不限制机器人 OCR 的原有分类。"""
        value = denomination.strip()
        if not value or len(value) > 60:
            raise ValueError("invalid denomination")
        return value

    def init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS card_manager_state (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );

                INSERT OR IGNORE INTO card_manager_state(name, value) VALUES ('change_version', 0);

                CREATE TABLE IF NOT EXISTS card_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_chat_id INTEGER NOT NULL,
                    telegram_chat_title TEXT NOT NULL DEFAULT '',
                    telegram_user_id INTEGER NOT NULL DEFAULT 0,
                    telegram_user_name TEXT NOT NULL DEFAULT '',
                    telegram_user_username TEXT NOT NULL DEFAULT '',
                    telegram_message_id INTEGER NOT NULL,
                    telegram_message_date TEXT NOT NULL,
                    media_group_id TEXT NOT NULL DEFAULT '',
                    image_index INTEGER NOT NULL DEFAULT 1,
                    card_index INTEGER NOT NULL DEFAULT 1,
                    display_order INTEGER NOT NULL,
                    card_type TEXT NOT NULL DEFAULT 'PUBG',
                    original_image_path TEXT NOT NULL DEFAULT '',
                    telegram_file_id TEXT NOT NULL DEFAULT '',
                    telegram_file_unique_id TEXT NOT NULL DEFAULT '',
                    image_cached_at TEXT NOT NULL DEFAULT '',
                    image_expires_at TEXT NOT NULL DEFAULT '',
                    ocr_original_card TEXT NOT NULL DEFAULT '',
                    final_card TEXT NOT NULL DEFAULT '',
                    denomination TEXT NOT NULL DEFAULT '未分类',
                    source_type TEXT NOT NULL CHECK (source_type IN ('OCR', 'MANUAL')),
                    is_manual_added INTEGER NOT NULL DEFAULT 0,
                    manual_added_at TEXT,
                    is_manually_edited INTEGER NOT NULL DEFAULT 0,
                    edited_at TEXT,
                    is_stocked INTEGER NOT NULL DEFAULT 0,
                    stocked_at TEXT,
                    is_redeemed INTEGER NOT NULL DEFAULT 0,
                    redeemed_at TEXT,
                    is_invalid INTEGER NOT NULL DEFAULT 0,
                    invalid_at TEXT,
                    is_duplicate INTEGER NOT NULL DEFAULT 0,
                    is_ocr_failed INTEGER NOT NULL DEFAULT 0,
                    is_viewed INTEGER NOT NULL DEFAULT 0,
                    viewed_at TEXT,
                    manual_note TEXT NOT NULL DEFAULT '',
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    change_version INTEGER NOT NULL DEFAULT 0
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_card_records_ocr_source
                    ON card_records(telegram_chat_id, telegram_message_id, image_index, card_index)
                    WHERE source_type = 'OCR';
                CREATE INDEX IF NOT EXISTS ix_card_records_display_order
                    ON card_records(telegram_message_date, telegram_message_id, image_index, display_order, id);
                CREATE INDEX IF NOT EXISTS ix_card_records_chat
                    ON card_records(telegram_chat_id, telegram_message_date, telegram_message_id, image_index, display_order);
                CREATE INDEX IF NOT EXISTS ix_card_records_final_card
                    ON card_records(final_card COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS ix_card_records_change_version
                    ON card_records(change_version);

                CREATE TABLE IF NOT EXISTS chat_aliases (
                    telegram_chat_id INTEGER PRIMARY KEY,
                    original_name TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    change_version INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS user_aliases (
                    telegram_user_id INTEGER PRIMARY KEY,
                    original_name TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    change_version INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS denomination_rules (
                    prefix TEXT PRIMARY KEY,
                    denomination TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            # 旧版管理端已有的记录默认视为已查看；新同步的记录会显式写入未读状态。
            self._ensure_column(connection, "card_records", "is_ocr_failed", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "card_records", "is_viewed", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(connection, "card_records", "viewed_at", "TEXT")
            self._ensure_column(connection, "card_records", "manual_note", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "card_records", "is_deleted", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "card_records", "deleted_at", "TEXT")
            self._migrate_denomination_rules(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_card_records_unread "
                "ON card_records(telegram_chat_id, is_viewed, is_stocked, telegram_message_date)"
            )
            connection.executemany(
                "INSERT OR IGNORE INTO denomination_rules(prefix, denomination, updated_at) VALUES (?, ?, ?)",
                [("S07368", "11200", self._now()), ("S07362", "11200", self._now()), ("S07367", "5500", self._now()), ("S07361", "5500", self._now())],
            )
            # 旧版按全部历史记录标记重复；迁移一次，改为按北京时间自然日判断。
            migrated = connection.execute(
                "INSERT OR IGNORE INTO card_manager_state(name, value) VALUES ('duplicate_scope_beijing_day', 1)"
            )
            if migrated.rowcount:
                self._rebuild_duplicate_flags(connection)

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _migrate_denomination_rules(connection: sqlite3.Connection) -> None:
        """移除旧版规则表对 11200/5500 的硬编码，不触及机器人 OCR 表。"""
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'denomination_rules'"
        ).fetchone()
        definition = str(row["sql"] or "") if row else ""
        if "CHECK (denomination IN ('11200', '5500'))" not in definition:
            return
        connection.executescript(
            """
            CREATE TABLE denomination_rules_new (
                prefix TEXT PRIMARY KEY,
                denomination TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO denomination_rules_new(prefix, denomination, updated_at)
                SELECT prefix, denomination, updated_at FROM denomination_rules;
            DROP TABLE denomination_rules;
            ALTER TABLE denomination_rules_new RENAME TO denomination_rules;
            """
        )

    def record_ocr_cards(self, records: Iterable[CardRecordInput]) -> list[int]:
        """保存最终 OCR 输出；同一 Telegram 图片重复投递时幂等。"""
        created_ids: list[int] = []
        with self._connect() as connection:
            for record in records:
                now = self._now()
                version = self._next_version(connection)
                denomination = record.denomination
                if denomination == "未分类":
                    denomination = self._denomination_for_card(connection, record.final_card)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO card_records (
                        telegram_chat_id, telegram_chat_title, telegram_user_id,
                        telegram_user_name, telegram_user_username, telegram_message_id,
                        telegram_message_date, media_group_id, image_index, card_index,
                        display_order, card_type, original_image_path, telegram_file_id,
                        telegram_file_unique_id, image_cached_at, image_expires_at,
                        ocr_original_card, final_card, denomination, source_type, is_ocr_failed, is_viewed,
                        created_at, updated_at, change_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OCR', ?, 0, ?, ?, ?)
                    """,
                    (
                        record.telegram_chat_id,
                        record.telegram_chat_title,
                        record.telegram_user_id,
                        record.telegram_user_name,
                        record.telegram_user_username,
                        record.telegram_message_id,
                        record.telegram_message_date,
                        record.media_group_id,
                        record.image_index,
                        record.card_index,
                        record.card_index * ORDER_GAP,
                        record.card_type,
                        record.original_image_path,
                        record.telegram_file_id,
                        record.telegram_file_unique_id,
                        record.image_cached_at,
                        record.image_expires_at,
                        record.ocr_original_card,
                        record.final_card,
                        denomination,
                        1 if record.ocr_failed else 0,
                        now,
                        now,
                        version,
                    ),
                )
                if cursor.rowcount:
                    created_ids.append(int(cursor.lastrowid))
                    self._refresh_duplicate_flag(connection, record.final_card)
                self._upsert_original_names(connection, record, now)
        return created_ids

    def list_records(
        self,
        *,
        chat_id: int | None = None,
        denomination: str | None = None,
        stocked: bool | None = None,
        redeemed: bool | None = None,
        duplicates_only: bool = False,
        unread_only: bool = False,
        search: str = "",
        after_version: int = 0,
        limit: int = 2000,
    ) -> list[dict[str, object]]:
        """按 Telegram 原始时间稳定排序读取管理端记录。"""
        # 图片仅用于当天人工核对；跨到新一天后释放缓存，卡密记录仍会保留。
        self.cleanup_images_before_today()
        clauses = ["r.is_deleted = 0", "r.change_version > ?"] if after_version > 0 else ["r.is_deleted = 0"]
        params: list[object] = [after_version] if after_version > 0 else []
        if chat_id is not None:
            clauses.append("r.telegram_chat_id = ?")
            params.append(chat_id)
        if denomination is not None:
            clauses.append("r.denomination = ?")
            params.append(denomination)
        if stocked is not None:
            clauses.append("r.is_stocked = ?")
            params.append(1 if stocked else 0)
        if redeemed is not None:
            clauses.append("r.is_redeemed = ?")
            params.append(1 if redeemed else 0)
        if duplicates_only:
            clauses.append("r.is_duplicate = 1")
        if unread_only:
            clauses.append("r.is_viewed = 0 AND r.is_stocked = 0")
        query = search.strip()
        if query:
            clauses.append(
                "("
                "r.final_card LIKE ? OR r.ocr_original_card LIKE ? OR "
                "r.telegram_chat_title LIKE ? OR r.telegram_user_name LIKE ? OR "
                "r.telegram_user_username LIKE ? OR ca.display_name LIKE ? OR ua.display_name LIKE ?"
                ")"
            )
            params.extend([f"%{query}%"] * 7)
        params.append(max(1, min(limit, 10000)))
        sql = f"""
            SELECT r.*,
                   COALESCE(NULLIF(ca.display_name, ''), r.telegram_chat_title) AS display_chat_name,
                   COALESCE(NULLIF(ua.display_name, ''), r.telegram_user_name) AS display_user_name
            FROM card_records AS r
            LEFT JOIN chat_aliases AS ca ON ca.telegram_chat_id = r.telegram_chat_id
            LEFT JOIN user_aliases AS ua ON ua.telegram_user_id = r.telegram_user_id
            WHERE {' AND '.join(clauses)}
            ORDER BY r.telegram_message_date ASC, r.telegram_message_id ASC,
                     r.image_index ASC, r.display_order ASC, r.id ASC
            LIMIT ?
        """
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def get_record(self, record_id: int) -> dict[str, object]:
        with self._connect() as connection:
            return self._record_with_names(connection, record_id)

    def list_chat_counts(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.telegram_chat_id,
                       COALESCE(NULLIF(ca.display_name, ''), MAX(r.telegram_chat_title)) AS display_chat_name,
                       COUNT(*) AS card_count
                FROM card_records AS r
                LEFT JOIN chat_aliases AS ca ON ca.telegram_chat_id = r.telegram_chat_id
                WHERE r.is_deleted = 0
                GROUP BY r.telegram_chat_id, ca.display_name
                ORDER BY display_chat_name COLLATE NOCASE, r.telegram_chat_id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def clear_chat_records(self, chat_id: int) -> int:
        """清空一个群的管理端列表，不触碰 Telegram 或机器人原始 OCR 数据。"""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT final_card FROM card_records WHERE telegram_chat_id = ? AND is_deleted = 0",
                (chat_id,),
            ).fetchall()
            if not rows:
                return 0
            now = self._now()
            version = self._next_version(connection)
            count = connection.execute(
                """
                UPDATE card_records
                SET is_deleted = 1, deleted_at = ?, updated_at = ?, change_version = ?
                WHERE telegram_chat_id = ? AND is_deleted = 0
                """,
                (now, now, version, chat_id),
            ).rowcount
            for row in rows:
                self._refresh_duplicate_flag(connection, str(row["final_card"]))
            return int(count)

    def delete_cards(self, record_ids: Iterable[int]) -> int:
        """一次隐藏多张管理端卡密，避免客户端逐张请求导致超时。"""
        ids = list(dict.fromkeys(int(record_id) for record_id in record_ids))
        if not ids:
            return 0
        with self._connect() as connection:
            placeholders = ", ".join("?" for _ in ids)
            rows = connection.execute(
                f"SELECT DISTINCT final_card FROM card_records WHERE id IN ({placeholders}) AND is_deleted = 0",
                ids,
            ).fetchall()
            if not rows:
                return 0
            now = self._now()
            version = self._next_version(connection)
            count = connection.execute(
                f"""
                UPDATE card_records
                SET is_deleted = 1, deleted_at = ?, updated_at = ?, change_version = ?
                WHERE id IN ({placeholders}) AND is_deleted = 0
                """,
                (now, now, version, *ids),
            ).rowcount
            for row in rows:
                self._refresh_duplicate_flag(connection, str(row["final_card"]))
            return int(count)

    def restore_deleted_cards(self, record_ids: Iterable[int]) -> list[dict[str, object]]:
        """恢复误删的管理端记录；只修改旁路表，绝不回写机器人来源。"""
        ids = list(dict.fromkeys(int(record_id) for record_id in record_ids))
        if not ids:
            return []
        with self._connect() as connection:
            placeholders = ", ".join("?" for _ in ids)
            rows = connection.execute(
                f"SELECT id, final_card FROM card_records WHERE id IN ({placeholders}) AND is_deleted = 1",
                ids,
            ).fetchall()
            if not rows:
                return []
            now = self._now()
            version = self._next_version(connection)
            restore_ids = [int(row["id"]) for row in rows]
            restore_placeholders = ", ".join("?" for _ in restore_ids)
            connection.execute(
                f"""
                UPDATE card_records
                SET is_deleted = 0, deleted_at = NULL, updated_at = ?, change_version = ?
                WHERE id IN ({restore_placeholders})
                """,
                (now, version, *restore_ids),
            )
            for row in rows:
                self._refresh_duplicate_flag(connection, str(row["final_card"]))
            return [self._record_with_names(connection, record_id) for record_id in restore_ids]

    def purge_records_before_previous_day(self, *, now: datetime | None = None) -> int:
        """永久清理北京时间前天及更早的管理端卡密和对应残留图片。"""
        local_zone = timezone(timedelta(hours=8))
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        cutoff_day = current.astimezone(local_zone).date() - timedelta(days=1)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, telegram_message_date, original_image_path FROM card_records"
            ).fetchall()
            expired_ids: list[int] = []
            for row in rows:
                try:
                    message_time = datetime.fromisoformat(str(row["telegram_message_date"]))
                    if message_time.tzinfo is None:
                        message_time = message_time.replace(tzinfo=UTC)
                    if message_time.astimezone(local_zone).date() >= cutoff_day:
                        continue
                except (TypeError, ValueError):
                    continue
                path = Path(str(row["original_image_path"] or ""))
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass
                expired_ids.append(int(row["id"]))
            if not expired_ids:
                return 0
            placeholders = ", ".join("?" for _ in expired_ids)
            self._next_version(connection)
            connection.execute(f"DELETE FROM card_records WHERE id IN ({placeholders})", expired_ids)
            return len(expired_ids)

    def current_change_version(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM card_manager_state WHERE name = 'change_version'").fetchone()
            return int(row["value"] if row else 0)

    def changes_since(self, version: int, *, limit: int = 2000) -> dict[str, object]:
        """为 REST 补同步与 WebSocket 推送提供同一版本游标。"""
        with self._connect() as connection:
            records = self.list_records(after_version=version, limit=limit)
            chats = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM chat_aliases WHERE change_version > ? ORDER BY change_version",
                    (version,),
                ).fetchall()
            ]
            users = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM user_aliases WHERE change_version > ? ORDER BY change_version",
                    (version,),
                ).fetchall()
            ]
            return {
                "version": self.current_change_version(),
                "records": records,
                "chat_aliases": chats,
                "user_aliases": users,
            }

    def statistics(self, **filters: object) -> dict[str, int]:
        records = self.list_records(limit=10000, **filters)
        total = len(records)
        redeemed = sum(int(row["is_redeemed"]) for row in records)
        invalid = sum(int(row["is_invalid"]) for row in records)
        stocked = sum(int(row["is_stocked"]) for row in records)
        return {
            "total": total,
            "11200": sum(row["denomination"] == "11200" for row in records),
            "5500": sum(row["denomination"] == "5500" for row in records),
            "unclassified": sum(row["denomination"] == "未分类" for row in records),
            "redeemed": redeemed,
            "invalid": invalid,
            "valid": total - redeemed - invalid,
            "stocked": stocked,
            "pending_stock": total - stocked,
        }

    def update_card(
        self,
        record_id: int,
        *,
        final_card: str | None = None,
        denomination: str | None = None,
        stocked: bool | None = None,
        redeemed: bool | None = None,
        invalid: bool | None = None,
        viewed: bool | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM card_records WHERE id = ?", (record_id,)).fetchone()
            if row is None:
                raise KeyError(record_id)
            values: dict[str, object] = {}
            now = self._now()
            if final_card is not None:
                values["final_card"] = final_card.strip().upper()
                values["is_manually_edited"] = 1
                values["edited_at"] = now
                if final_card.strip():
                    values["is_ocr_failed"] = 0
            if denomination is not None:
                values["denomination"] = self._normalize_denomination(denomination)
            if redeemed is not None:
                values["is_redeemed"] = 1 if redeemed else 0
                values["redeemed_at"] = now if redeemed else None
                if redeemed:
                    values["is_stocked"] = 0
                    values["stocked_at"] = None
            if stocked is not None:
                if stocked and (redeemed if redeemed is not None else bool(row["is_redeemed"])):
                    raise ValueError("redeemed card cannot be stocked")
                values["is_stocked"] = 1 if stocked else 0
                values["stocked_at"] = now if stocked else None
                if stocked:
                    values["is_viewed"] = 1
                    values["viewed_at"] = now
            if viewed is not None:
                values["is_viewed"] = 1 if viewed else 0
                values["viewed_at"] = now if viewed else None
            if note is not None:
                values["manual_note"] = note.strip()[:300]
            if invalid is not None:
                values["is_invalid"] = 1 if invalid else 0
                values["invalid_at"] = now if invalid else None
            if not values:
                return self._record_with_names(connection, record_id)
            values["updated_at"] = now
            values["change_version"] = self._next_version(connection)
            assignments = ", ".join(f"{name} = ?" for name in values)
            connection.execute(f"UPDATE card_records SET {assignments} WHERE id = ?", [*values.values(), record_id])
            self._refresh_duplicate_flag(connection, str(values.get("final_card", row["final_card"])))
            return self._record_with_names(connection, record_id)

    def update_cards_batch(
        self,
        record_ids: Iterable[int],
        *,
        denomination: str | None = None,
        stocked: bool | None = None,
        redeemed: bool | None = None,
        invalid: bool | None = None,
    ) -> list[dict[str, object]]:
        """一次提交多条管理端状态，避免逐条刷新造成界面闪烁。"""
        ids = list(dict.fromkeys(int(record_id) for record_id in record_ids))
        if not ids:
            return []
        if denomination is not None:
            denomination = self._normalize_denomination(denomination)
        with self._connect() as connection:
            placeholders = ", ".join("?" for _ in ids)
            rows = connection.execute(
                f"SELECT * FROM card_records WHERE id IN ({placeholders}) AND is_deleted = 0",
                ids,
            ).fetchall()
            by_id = {int(row["id"]): row for row in rows}
            if len(by_id) != len(ids):
                missing = next(record_id for record_id in ids if record_id not in by_id)
                raise KeyError(missing)
            if denomination is None and stocked is None and redeemed is None and invalid is None:
                return [self._record_with_names(connection, record_id) for record_id in ids]
            now = self._now()
            version = self._next_version(connection)
            for record_id in ids:
                row = by_id[record_id]
                values: dict[str, object] = {}
                if denomination is not None:
                    values["denomination"] = denomination
                if redeemed is not None:
                    values["is_redeemed"] = 1 if redeemed else 0
                    values["redeemed_at"] = now if redeemed else None
                    if redeemed:
                        values["is_stocked"] = 0
                        values["stocked_at"] = None
                if stocked is not None:
                    if stocked and (redeemed if redeemed is not None else bool(row["is_redeemed"])):
                        raise ValueError("redeemed card cannot be stocked")
                    values["is_stocked"] = 1 if stocked else 0
                    values["stocked_at"] = now if stocked else None
                    if stocked:
                        values["is_viewed"] = 1
                        values["viewed_at"] = now
                if invalid is not None:
                    values["is_invalid"] = 1 if invalid else 0
                    values["invalid_at"] = now if invalid else None
                values["updated_at"] = now
                values["change_version"] = version
                assignments = ", ".join(f"{name} = ?" for name in values)
                connection.execute(f"UPDATE card_records SET {assignments} WHERE id = ?", [*values.values(), record_id])
            return [self._record_with_names(connection, record_id) for record_id in ids]

    def insert_manual_card(self, record_id: int, *, after: bool, denomination: str | None = None) -> dict[str, object]:
        """在同一 Telegram 原图内插入一条真实的人工卡密记录。"""
        with self._connect() as connection:
            target = connection.execute("SELECT * FROM card_records WHERE id = ?", (record_id,)).fetchone()
            if target is None:
                raise KeyError(record_id)
            sibling_clause = "telegram_chat_id = ? AND telegram_message_id = ? AND media_group_id = ? AND image_index = ?"
            sibling_params = (
                target["telegram_chat_id"], target["telegram_message_id"], target["media_group_id"], target["image_index"],
            )
            if after:
                neighbor = connection.execute(
                    f"SELECT display_order FROM card_records WHERE {sibling_clause} AND display_order > ? ORDER BY display_order, id LIMIT 1",
                    (*sibling_params, target["display_order"]),
                ).fetchone()
                lower, upper = int(target["display_order"]), int(neighbor["display_order"]) if neighbor else None
            else:
                neighbor = connection.execute(
                    f"SELECT display_order FROM card_records WHERE {sibling_clause} AND display_order < ? ORDER BY display_order DESC, id DESC LIMIT 1",
                    (*sibling_params, target["display_order"]),
                ).fetchone()
                lower, upper = int(neighbor["display_order"]) if neighbor else None, int(target["display_order"])
            display_order = self._between_order(connection, sibling_clause, sibling_params, lower, upper)
            now = self._now()
            version = self._next_version(connection)
            assigned_denomination = denomination or str(target["denomination"])
            cursor = connection.execute(
                """
                INSERT INTO card_records (
                    telegram_chat_id, telegram_chat_title, telegram_user_id, telegram_user_name,
                    telegram_user_username, telegram_message_id, telegram_message_date, media_group_id,
                    image_index, card_index, display_order, card_type, original_image_path,
                    telegram_file_id, telegram_file_unique_id, image_cached_at, image_expires_at,
                    denomination, source_type, is_manual_added, manual_added_at,
                    created_at, updated_at, change_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MANUAL', 1, ?, ?, ?, ?)
                """,
                (
                    target["telegram_chat_id"], target["telegram_chat_title"], target["telegram_user_id"],
                    target["telegram_user_name"], target["telegram_user_username"], target["telegram_message_id"],
                    target["telegram_message_date"], target["media_group_id"], target["image_index"],
                    target["card_index"], display_order, target["card_type"], target["original_image_path"],
                    target["telegram_file_id"], target["telegram_file_unique_id"], target["image_cached_at"],
                    target["image_expires_at"], assigned_denomination, now, now, now, version,
                ),
            )
            return self._record_with_names(connection, int(cursor.lastrowid))

    def create_manual_card(
        self,
        *,
        final_card: str,
        denomination: str,
        chat_name: str,
        user_name: str,
    ) -> dict[str, object]:
        """创建不依附 Telegram 原图的管理端人工卡密。"""
        card = final_card.strip().upper()
        chat = chat_name.strip()
        user = user_name.strip()
        if not card:
            raise ValueError("卡密不能为空")
        denomination = denomination.strip()
        if not denomination:
            raise ValueError("面值或卡种不能为空")
        if not chat:
            raise ValueError("群名不能为空")
        if not user:
            raise ValueError("发送用户不能为空")
        with self._connect() as connection:
            chat_id = self._manual_entity_id(connection, "telegram_chat_id", "telegram_chat_title", chat)
            user_id = self._manual_entity_id(connection, "telegram_user_id", "telegram_user_name", user)
            now = self._now()
            version = self._next_version(connection)
            display_order = self._next_manual_display_order(connection, chat_id)
            cursor = connection.execute(
                """
                INSERT INTO card_records (
                    telegram_chat_id, telegram_chat_title, telegram_user_id, telegram_user_name,
                    telegram_user_username, telegram_message_id, telegram_message_date, media_group_id,
                    image_index, card_index, display_order, card_type, original_image_path,
                    telegram_file_id, telegram_file_unique_id, image_cached_at, image_expires_at,
                    ocr_original_card, final_card, denomination, source_type, is_manual_added,
                    is_viewed, manual_added_at, created_at, updated_at, change_version
                ) VALUES (?, ?, ?, ?, '', 0, ?, 'manual', 1, 1, ?, 'MANUAL', '', '', '', '', '', ?, ?, ?, 'MANUAL', 1, 1, ?, ?, ?, ?)
                """,
                (
                    chat_id, chat, user_id, user, now, display_order,
                    card, card, denomination, now, now, now, version,
                ),
            )
            self._refresh_duplicate_flag(connection, card)
            return self._record_with_names(connection, int(cursor.lastrowid))

    def delete_manual_card(self, record_id: int) -> bool:
        return self.delete_card(record_id)

    def delete_card(self, record_id: int) -> bool:
        """仅在管理端隐藏记录；绝不删除 Telegram 原消息或影响 OCR 历史。"""
        with self._connect() as connection:
            row = connection.execute("SELECT final_card FROM card_records WHERE id = ? AND is_deleted = 0", (record_id,)).fetchone()
            if row is None:
                return False
            now = self._now()
            version = self._next_version(connection)
            connection.execute(
                "UPDATE card_records SET is_deleted = 1, deleted_at = ?, updated_at = ?, change_version = ? WHERE id = ?",
                (now, now, version, record_id),
            )
            self._refresh_duplicate_flag(connection, str(row["final_card"]))
            return True

    def _between_order(
        self,
        connection: sqlite3.Connection,
        sibling_clause: str,
        sibling_params: tuple[object, ...],
        lower: int | None,
        upper: int | None,
    ) -> int:
        if lower is None and upper is None:
            return ORDER_GAP
        if lower is None:
            return upper - ORDER_GAP if upper and upper > ORDER_GAP else max(1, upper // 2)
        if upper is None:
            return lower + ORDER_GAP
        if upper - lower > 1:
            return lower + (upper - lower) // 2
        rows = connection.execute(
            f"SELECT id FROM card_records WHERE {sibling_clause} ORDER BY display_order, id",
            sibling_params,
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            connection.execute("UPDATE card_records SET display_order = ? WHERE id = ?", (index * ORDER_GAP, row["id"]))
        return lower + ORDER_GAP // 2

    @staticmethod
    def _manual_entity_id(connection: sqlite3.Connection, id_column: str, name_column: str, name: str) -> int:
        existing = connection.execute(
            f"SELECT {id_column} FROM card_records WHERE source_type = 'MANUAL' AND {name_column} = ? ORDER BY id LIMIT 1",
            (name,),
        ).fetchone()
        if existing is not None:
            return int(existing[id_column])
        previous = connection.execute(
            f"SELECT MIN({id_column}) AS id FROM card_records WHERE source_type = 'MANUAL' AND {id_column} <= ?",
            (MANUAL_ID_BASE,),
        ).fetchone()
        return MANUAL_ID_BASE if previous is None or previous["id"] is None else int(previous["id"]) - 1

    @staticmethod
    def _next_manual_display_order(connection: sqlite3.Connection, chat_id: int) -> int:
        row = connection.execute(
            "SELECT MAX(display_order) AS value FROM card_records WHERE telegram_chat_id = ? AND source_type = 'MANUAL'",
            (chat_id,),
        ).fetchone()
        return int(row["value"] or 0) + ORDER_GAP

    def set_chat_alias(self, chat_id: int, display_name: str) -> None:
        with self._connect() as connection:
            now = self._now()
            version = self._next_version(connection)
            connection.execute(
                """
                INSERT INTO chat_aliases(telegram_chat_id, display_name, updated_at, change_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_chat_id) DO UPDATE SET
                    display_name = excluded.display_name, updated_at = excluded.updated_at,
                    change_version = excluded.change_version
                """,
                (chat_id, display_name.strip(), now, version),
            )

    def set_user_alias(self, user_id: int, display_name: str) -> None:
        with self._connect() as connection:
            now = self._now()
            version = self._next_version(connection)
            connection.execute(
                """
                INSERT INTO user_aliases(telegram_user_id, display_name, updated_at, change_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    display_name = excluded.display_name, updated_at = excluded.updated_at,
                    change_version = excluded.change_version
                """,
                (user_id, display_name.strip(), now, version),
            )

    def list_denomination_rules(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM denomination_rules ORDER BY length(prefix) DESC, prefix").fetchall()]

    def set_denomination_rule(self, prefix: str, denomination: str) -> None:
        normalized = prefix.strip().upper()
        denomination = self._normalize_denomination(denomination)
        # PSN 没有稳定前缀规则；规则仅服务 PUBG S07 卡密，PSN 面额由人工设置。
        if not normalized.startswith("S07"):
            raise ValueError("prefix rules only support PUBG S07 cards")
        with self._connect() as connection:
            now = self._now()
            version = self._next_version(connection)
            connection.execute(
                """
                INSERT INTO denomination_rules(prefix, denomination, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(prefix) DO UPDATE SET denomination = excluded.denomination, updated_at = excluded.updated_at
                """,
                (normalized, denomination, now),
            )
            # 已存在但尚未分类的记录也可立即按新规则归类；人工已分类的记录不动。
            connection.execute(
                """
                UPDATE card_records
                SET denomination = ?, updated_at = ?, change_version = ?
                WHERE denomination = '未分类' AND final_card LIKE ?
                """,
                (denomination, now, version, f"{normalized}%"),
            )

    def delete_denomination_rule(self, prefix: str) -> bool:
        with self._connect() as connection:
            return connection.execute("DELETE FROM denomination_rules WHERE prefix = ?", (prefix.strip().upper(),)).rowcount > 0

    def _denomination_for_card(self, connection: sqlite3.Connection, card: str) -> str:
        normalized = card.strip().upper()
        if not normalized.startswith("S07"):
            return "未分类"
        row = connection.execute(
            "SELECT denomination FROM denomination_rules WHERE ? LIKE prefix || '%' ORDER BY length(prefix) DESC LIMIT 1",
            (normalized,),
        ).fetchone()
        return str(row["denomination"]) if row else "未分类"

    def health_summary(self) -> dict[str, object]:
        """管理端健康摘要；仅读取旁路表，不影响 Telegram、OCR 或账本。"""
        self.cleanup_images_before_today()
        local_zone = timezone(timedelta(hours=8))
        today = datetime.now(local_zone).date()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT telegram_message_date, final_card, is_ocr_failed, is_invalid,
                       original_image_path, image_expires_at
                FROM card_records WHERE is_deleted = 0
                """
            ).fetchall()
        latest_valid = ""
        today_new = 0
        images_cached = 0
        images_expired = 0
        for row in rows:
            value = str(row["telegram_message_date"] or "")
            try:
                moment = datetime.fromisoformat(value)
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=UTC)
                local_moment = moment.astimezone(local_zone)
                if local_moment.date() == today:
                    today_new += 1
            except ValueError:
                pass
            if str(row["final_card"] or "").strip() and not row["is_ocr_failed"] and not row["is_invalid"]:
                latest_valid = max(latest_valid, value)
            path = Path(str(row["original_image_path"] or ""))
            if path.is_file():
                images_cached += 1
            elif str(row["image_expires_at"] or ""):
                images_expired += 1
        return {
            "last_valid_card_at": latest_valid,
            "today_new": today_new,
            "image_cache": {"cached": images_cached, "expired": images_expired},
        }

    def cleanup_images_before_today(self, *, now: datetime | None = None) -> int:
        """删除北京时间昨天及更早的管理端原图，不删除卡密或 Telegram 数据。"""
        local_zone = timezone(timedelta(hours=8))
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        today = current.astimezone(local_zone).date()
        expired_ids: list[int] = []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, telegram_message_date, original_image_path
                FROM card_records
                WHERE is_deleted = 0
                  AND image_cached_at <> ''
                  AND original_image_path <> ''
                """
            ).fetchall()
            for row in rows:
                try:
                    message_time = datetime.fromisoformat(str(row["telegram_message_date"]))
                    if message_time.tzinfo is None:
                        message_time = message_time.replace(tzinfo=UTC)
                    if message_time.astimezone(local_zone).date() >= today:
                        continue
                except (TypeError, ValueError):
                    continue
                try:
                    path = Path(str(row["original_image_path"]))
                    if path.is_file():
                        path.unlink()
                except OSError:
                    continue
                expired_ids.append(int(row["id"]))
            if expired_ids:
                connection.executemany(
                    "UPDATE card_records SET original_image_path = '', image_expires_at = ? WHERE id = ?",
                    [(current.isoformat(timespec="seconds"), record_id) for record_id in expired_ids],
                )
        return len(expired_ids)

    def _record_with_names(self, connection: sqlite3.Connection, record_id: int) -> dict[str, object]:
        row = connection.execute(
            """
            SELECT r.*, COALESCE(NULLIF(ca.display_name, ''), r.telegram_chat_title) AS display_chat_name,
                   COALESCE(NULLIF(ua.display_name, ''), r.telegram_user_name) AS display_user_name
            FROM card_records AS r
            LEFT JOIN chat_aliases AS ca ON ca.telegram_chat_id = r.telegram_chat_id
            LEFT JOIN user_aliases AS ua ON ua.telegram_user_id = r.telegram_user_id
            WHERE r.id = ?
            """,
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return dict(row)

    def _upsert_original_names(self, connection: sqlite3.Connection, record: CardRecordInput, now: str) -> None:
        chat_version = self._next_version(connection)
        connection.execute(
            """
            INSERT INTO chat_aliases(telegram_chat_id, original_name, updated_at, change_version)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_chat_id) DO UPDATE SET
                original_name = excluded.original_name,
                updated_at = excluded.updated_at,
                change_version = excluded.change_version
            """,
            (record.telegram_chat_id, record.telegram_chat_title, now, chat_version),
        )
        if record.telegram_user_id:
            user_version = self._next_version(connection)
            connection.execute(
                """
                INSERT INTO user_aliases(telegram_user_id, original_name, updated_at, change_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    original_name = excluded.original_name,
                    updated_at = excluded.updated_at,
                    change_version = excluded.change_version
                """,
                (record.telegram_user_id, record.telegram_user_name, now, user_version),
            )

    def _next_version(self, connection: sqlite3.Connection) -> int:
        connection.execute("UPDATE card_manager_state SET value = value + 1 WHERE name = 'change_version'")
        row = connection.execute("SELECT value FROM card_manager_state WHERE name = 'change_version'").fetchone()
        return int(row["value"])

    def _refresh_duplicate_flag(self, connection: sqlite3.Connection, card: str) -> None:
        normalized = card.strip()
        if not normalized:
            return
        connection.execute(
            """
            UPDATE card_records AS current
            SET is_duplicate = CASE WHEN (
                SELECT COUNT(*)
                FROM card_records AS candidate
                WHERE candidate.is_deleted = 0
                  AND candidate.final_card <> ''
                  AND lower(candidate.final_card) = lower(?)
                  AND date(candidate.telegram_message_date, '+8 hours') = date(current.telegram_message_date, '+8 hours')
            ) > 1 THEN 1 ELSE 0 END
            WHERE current.is_deleted = 0
              AND current.final_card <> ''
              AND lower(current.final_card) = lower(?)
            """,
            (normalized, normalized),
        )

    @staticmethod
    def _rebuild_duplicate_flags(connection: sqlite3.Connection) -> None:
        """将旧版全历史重复标记一次性迁移为北京时间当天内的重复标记。"""
        connection.execute(
            """
            UPDATE card_records AS current
            SET is_duplicate = CASE WHEN (
                SELECT COUNT(*)
                FROM card_records AS candidate
                WHERE candidate.is_deleted = 0
                  AND candidate.final_card <> ''
                  AND lower(candidate.final_card) = lower(current.final_card)
                  AND date(candidate.telegram_message_date, '+8 hours') = date(current.telegram_message_date, '+8 hours')
            ) > 1 THEN 1 ELSE 0 END
            WHERE current.is_deleted = 0
            """
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")
