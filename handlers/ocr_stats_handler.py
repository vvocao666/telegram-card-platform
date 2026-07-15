from __future__ import annotations

import asyncio
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from services.ocr.audit_cache import DEFAULT_AUDIT_ROOT
from services.ocr.daily_stats_report import SHANGHAI_TZ, collect_daily_ocr_stats, format_chat_daily_ocr_stats


async def group_daily_ocr_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """回复当前群北京时间当天按用户合并的卡密识别统计。"""
    del context
    message = update.effective_message
    chat = update.effective_chat
    if message is None:
        return
    if chat is None or chat.type not in {"group", "supergroup"}:
        await message.reply_text("该命令仅限群聊使用。")
        return

    report_date = datetime.now(SHANGHAI_TZ).date()
    stats = await asyncio.to_thread(collect_daily_ocr_stats, DEFAULT_AUDIT_ROOT, report_date)
    for text in format_chat_daily_ocr_stats(stats, chat.id):
        await message.reply_text(text, parse_mode="HTML")
