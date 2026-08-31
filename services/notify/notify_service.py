from __future__ import annotations

import asyncio
import html
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


UpdatePredicate = Callable[[Update | None], bool]
UpdateRecorder = Callable[[Update], None]


def extract_notify_all_text(text: str) -> str:
    stripped = text.strip()
    for command in ("通知所有人", "/notify_all", "/at_all"):
        if stripped == command:
            return ""
        if stripped.startswith(command):
            return stripped[len(command) :].strip()
    return ""


def html_mention_for_member(row: Any) -> str:
    username = (row["username"] or "").strip()
    if username:
        return "@" + html.escape(username.lstrip("@"))
    display_name = html.escape((row["display_name"] or "").strip() or str(row["user_id"]))
    return f'<a href="tg://user?id={int(row["user_id"])}">{display_name}</a>'


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


@dataclass(slots=True)
class NotifyController:
    """封装当前群成员通知，严格限制在触发命令所在群。"""

    ledger_store: Any
    is_group_update: UpdatePredicate
    can_use_group_notify: UpdatePredicate
    remember_bot_chat: UpdateRecorder
    remember_ledger_user: UpdateRecorder
    cooldowns: dict[int, float]

    async def notify_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not self.is_group_update(update):
            return
        self.remember_bot_chat(update)
        self.remember_ledger_user(update)
        if not self.can_use_group_notify(update):
            await update.message.reply_text("无权限。")
            return
        chat_id = update.effective_chat.id
        now = time.monotonic()
        last_sent_at = self.cooldowns.get(chat_id)
        if last_sent_at is not None and now - last_sent_at < 300:
            await update.message.reply_text(f"通知所有人冷却中，请 {int(300 - (now - last_sent_at))} 秒后再试。")
            return
        members = self.ledger_store.list_active_known_members(chat_id, days=30)
        mentions = [html_mention_for_member(row) for row in members]
        if not mentions:
            await update.message.reply_text("当前群没有最近30天活跃成员缓存。")
            return
        content = extract_notify_all_text(update.message.text or "")
        self.cooldowns[chat_id] = now
        chunks = chunked(mentions, 50)
        for index, mention_chunk in enumerate(chunks):
            parts = ["📢 通知所有人"]
            if content and index == 0:
                parts.extend(["", html.escape(content)])
            parts.extend(["", " ".join(mention_chunk)])
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(parts),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            if index < len(chunks) - 1:
                await asyncio.sleep(1)

    async def notify_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not self.is_group_update(update):
            return
        self.remember_bot_chat(update)
        self.remember_ledger_user(update)
        if not self.can_use_group_notify(update):
            await update.message.reply_text("无权限。")
            return
        chat_id = update.effective_chat.id
        total = self.ledger_store.count_active_known_members(chat_id)
        recent_7 = self.ledger_store.count_active_known_members(chat_id, days=7)
        recent_30 = self.ledger_store.count_active_known_members(chat_id, days=30)
        await update.message.reply_text(
            "当前群成员缓存\n"
            f"缓存人数：{total}\n"
            f"最近7天活跃：{recent_7}\n"
            f"最近30天活跃：{recent_30}"
        )
