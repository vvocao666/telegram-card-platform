from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from handlers.admin_handler import is_owner_update
from services.group.message_cleanup import can_delete_group_messages, delete_message_range


logger = logging.getLogger(__name__)


def enqueue_group_cleanup(context, chat_id: int, chat_type: str, chat_data: dict, message_id: int, failure_message=None):
    tasks = context.bot_data.setdefault("group_message_cleanup_tasks", {})
    logger.info("Group cleanup request active=%s message_id=%s", chat_id in tasks, message_id)
    if chat_id in tasks:
        chat_data["message_cleanup_requested_through"] = max(chat_data["message_cleanup_requested_through"], message_id)
        return tasks[chat_id]
    first_id = chat_data.get("message_cleanup_completed_through", 0) + 1
    chat_data["message_cleanup_requested_through"] = message_id

    async def run_cleanup() -> bool:
        try:
            completed_id = await delete_message_range(
                context.bot, chat_id, chat_type, first_id, message_id,
                lambda: chat_data["message_cleanup_requested_through"],
            )
            chat_data["message_cleanup_completed_through"] = completed_id
            logger.info("Group cleanup completed through message_id=%s", completed_id)
            return True
        except TelegramError as exc:
            logger.warning("Group message cleanup interrupted by Telegram API: %s", type(exc).__name__)
            if failure_message is not None:
                try:
                    await failure_message.reply_text(
                        "清理中断，部分消息可能已删除；请检查机器人权限及网络后重新发送 /del。",
                        do_quote=False,
                    )
                except TelegramError:
                    logger.warning("Could not send group message cleanup failure notice")
            return False
        finally:
            tasks.pop(chat_id, None)
            chat_data.pop("message_cleanup_requested_through", None)

    tasks[chat_id] = asyncio.create_task(run_cleanup())
    return tasks[chat_id]


async def delete_group_messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    chat = update.effective_chat
    if message is None or chat is None:
        return
    if chat.type == "private":
        from handlers.message_cleanup_menu import start_cleanup_menu

        await start_cleanup_menu(update, context)
        return
    if chat.type not in {"group", "supergroup"}:
        await message.reply_text("请在需要清理的群内发送 /del。", do_quote=False)
        return
    if message.sender_chat is not None or not is_owner_update(update):
        await message.reply_text("只有机器人主人可以使用 /del。", do_quote=False)
        return
    if context.args:
        await message.reply_text("直接发送 /del，清理当前群未满 48 小时的可删除消息。", do_quote=False)
        return
    if datetime.now(timezone.utc) - message.date >= timedelta(hours=48):
        await message.reply_text("这条 /del 已过期，请重新发送。", do_quote=False)
        return
    try:
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
    except TelegramError:
        await message.reply_text("暂时无法确认机器人权限，未开始清理，请稍后重试。", do_quote=False)
        return
    if not can_delete_group_messages(member, chat.type):
        return
    enqueue_group_cleanup(context, chat.id, chat.type, context.chat_data, message.message_id, message)
