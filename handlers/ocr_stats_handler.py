from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from services.ocr.audit_cache import DEFAULT_AUDIT_ROOT
from services.ocr.daily_stats_report import (
    SHANGHAI_TZ,
    OcrStatsTimeRangeError,
    collect_daily_ocr_stats,
    format_chat_daily_ocr_stats,
    parse_ocr_stats_time_range,
)


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

    command_time = _message_time(message)
    try:
        stats_range = parse_ocr_stats_time_range(str(getattr(message, "text", "") or ""), command_time)
    except OcrStatsTimeRangeError as exc:
        await message.reply_text(str(exc))
        return
    report_date = stats_range.start_at.date()
    owner_id = _owner_user_id()
    excluded_user_ids = {owner_id} if owner_id is not None else set()
    stats = await asyncio.to_thread(
        collect_daily_ocr_stats,
        DEFAULT_AUDIT_ROOT,
        report_date,
        excluded_user_ids=excluded_user_ids,
        start_at=stats_range.start_at,
        end_at=stats_range.end_at,
    )
    for text in format_chat_daily_ocr_stats(stats, chat.id, excluded_user_ids=excluded_user_ids):
        await message.reply_text(text, parse_mode="HTML")


def _owner_user_id() -> int | None:
    """延迟读取全局机器人 owner，避免 handler 注册阶段形成循环依赖。"""
    from services.runtime import owner_user_id

    return owner_user_id()


def _message_time(message: object) -> datetime:
    value = getattr(message, "date", None)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(SHANGHAI_TZ)
    return datetime.now(SHANGHAI_TZ)
