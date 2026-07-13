from __future__ import annotations

import html
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


def member_html_mention(member: Any) -> str:
    display_name = getattr(member, "full_name", "") or " ".join(
        part for part in (getattr(member, "first_name", ""), getattr(member, "last_name", "")) if part
    )
    display_name = display_name or getattr(member, "username", "") or "新成员"
    escaped_name = html.escape(str(display_name))
    username = str(getattr(member, "username", "") or "").lstrip("@")
    if username:
        return f'<a href="https://t.me/{html.escape(username)}">{escaped_name}</a>'
    return f'<a href="tg://user?id={int(member.id)}">{escaped_name}</a>'


def is_human_member(member: Any, bot_user_id: int) -> bool:
    return bool(member and int(getattr(member, "id", 0) or 0) != bot_user_id and not getattr(member, "is_bot", False))


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


async def handle_new_chat_members(
    update: Any,
    context: Any,
    hooks: GroupLifecycleHooks,
    bot_user_id: int,
) -> None:
    if not update.message or not update.effective_chat:
        return
    for member in update.message.new_chat_members or []:
        if int(getattr(member, "id", 0) or 0) == bot_user_id:
            inviter_id = update.effective_user.id if update.effective_user else 0
            if inviter_id:
                hooks.store.set_chat_owner(update.effective_chat.id, inviter_id)
            continue
        if not is_human_member(member, bot_user_id):
            continue
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"💐欢迎{member_html_mention(member)}加入该群~",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def handle_left_chat_member(
    update: Any,
    context: Any,
    hooks: GroupLifecycleHooks,
    bot_user_id: int,
) -> None:
    if not update.message or not update.effective_chat:
        return
    member = update.message.left_chat_member
    if not is_human_member(member, bot_user_id):
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{member_html_mention(member)}离开了本群，聚是满天星，散是一团火~",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
