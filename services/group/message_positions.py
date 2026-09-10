from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path

from telegram.request import HTTPXRequest


logger = logging.getLogger(__name__)


class GroupMessagePositions:
    """Keep only each group's highest observed message ID, never message contents."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS positions (chat_id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL)")

    def record_result(self, result) -> None:
        positions = {}
        for item in result if isinstance(result, list) else [result]:
            if not isinstance(item, dict):
                continue
            message = item.get("message") or item.get("edited_message") or item
            chat = message.get("chat", {})
            message_id = message.get("message_id", 0)
            if chat.get("type") in {"group", "supergroup"} and message_id > 0:
                chat_id = chat["id"]
                positions[chat_id] = max(positions.get(chat_id, 0), message_id)
        if positions:
            with sqlite3.connect(self.path) as db:
                db.executemany(
                    "INSERT INTO positions VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE "
                    "SET message_id = MAX(message_id, excluded.message_id)", positions.items(),
                )

    def latest(self, chat_id: int) -> int:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT message_id FROM positions WHERE chat_id = ?", (chat_id,)).fetchone()
        return row[0] if row else 0


class PositionTrackingRequest(HTTPXRequest):
    def __init__(self, *, positions: GroupMessagePositions, **kwargs) -> None:
        super().__init__(**kwargs)
        self.positions = positions

    async def do_request(self, *args, **kwargs):
        status, payload = await super().do_request(*args, **kwargs)
        if status == 200:
            try:
                result = json.loads(payload)
                if result.get("ok"):
                    await asyncio.to_thread(self.positions.record_result, result.get("result"))
            except Exception:
                # A metadata failure must never interrupt Telegram intake or OCR replies.
                logger.warning("Could not record group message position")
        return status, payload
