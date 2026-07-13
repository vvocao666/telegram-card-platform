from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode


@dataclass(frozen=True)
class GroupLifecycleHooks:
    store: Any
    welcome_sent_at: dict[int, float]
    welcome_message: Callable[[], str]
    monotonic: Callable[[], float] = time.monotonic


async def handle_bot_chat_member(update: Any, context: Any, hooks: GroupLifecycleHooks) -> None:
    if not update.my_chat_member or not update.effective_chat:
        return
    chat = update.effective_chat
    chat_type = getattr(chat, "type", "")
    if chat_type not in {"group", "supergroup"}:
        return
    old_status = getattr(update.my_chat_member.old_chat_member, "status", "")
    new_status = getattr(update.my_chat_member.new_chat_member, "status", "")
    if old_status not in {"left", "kicked"} or new_status not in {"member", "administrator"}:
        return
    now = hooks.monotonic()
    if now - hooks.welcome_sent_at.get(chat.id, 0) < 300:
        return
    hooks.welcome_sent_at[chat.id] = now
    title = getattr(chat, "title", "") or str(chat.id)
    hooks.store.remember_bot_chat(chat.id, title, chat_type)
    hooks.store.ensure_chat(chat.id)
    inviter_id = update.effective_user.id if update.effective_user else 0
    if inviter_id:
        hooks.store.set_chat_owner(chat.id, inviter_id)
    await context.bot.send_message(
        chat_id=chat.id,
        text=hooks.welcome_message(),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("使用说明", callback_data="ledger:help")]]),
        disable_web_page_preview=True,
    )
