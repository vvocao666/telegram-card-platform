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


async def delete_group_messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    chat = update.effective_chat
    if message is None or chat is None:
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
    tasks = context.bot_data.setdefault("group_message_cleanup_tasks", {})
    if chat.id in tasks:
        await message.reply_text("本群正在清理，请等待完成。", do_quote=False)
        return
    try:
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
    except TelegramError:
        await message.reply_text("暂时无法确认机器人权限，未开始清理，请稍后重试。", do_quote=False)
        return
    if not can_delete_group_messages(member, chat.type):
        await message.reply_text("请先将机器人设为管理员，并开启“删除消息”权限。", do_quote=False)
        return
    status = await message.reply_text(
        "正在清理本群未满 48 小时的可删除消息；历史记录较多时需要等待。", do_quote=False
    )
    first_id = context.chat_data.get("message_cleanup_completed_through", 0) + 1

    async def run_cleanup() -> None:
        try:
            await delete_message_range(context.bot, chat.id, chat.type, first_id, message.message_id)
            context.chat_data["message_cleanup_completed_through"] = message.message_id
            result = "本次清理完成。超过 48 小时、不可删除的系统消息及清理开始后的新消息会保留。"
        except TelegramError:
            logger.warning("Group message cleanup interrupted by Telegram API")
            result = "清理中断，部分消息可能已删除；请检查机器人权限及网络后重新发送 /del。"
        finally:
            tasks.pop(chat.id, None)
        try:
            await status.edit_text(result)
        except TelegramError:
            logger.warning("Could not update group message cleanup status")

    tasks[chat.id] = asyncio.create_task(run_cleanup())

