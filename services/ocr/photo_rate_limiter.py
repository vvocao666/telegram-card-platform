from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

from telegram import Update


photo_rate_chat: dict[int, list[float]] = defaultdict(list)
photo_rate_user: dict[tuple[int, int], list[float]] = defaultdict(list)
photo_rate_warned_at: dict[tuple[str, int], float] = {}


def _trim_rate_window(records: list[float], now: float, window_seconds: int) -> None:
    cutoff = now - window_seconds
    while records and records[0] < cutoff:
        records.pop(0)


def check_photo_rate_limit(
    update: Update,
    *,
    now: float | None,
    is_owner: Callable[[Update], bool],
    window_seconds: int,
    chat_limit: int,
    user_limit: int,
) -> str | None:
    if not update.message or not update.effective_chat:
        return "消息无效"
    if is_owner(update):
        return None
    current_time = now if now is not None else time.time()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id if update.effective_user else 0

    chat_records = photo_rate_chat[chat_id]
    _trim_rate_window(chat_records, current_time, window_seconds)
    if len(chat_records) >= chat_limit:
        return f"当前群图片发送太快，{window_seconds}秒内最多处理{chat_limit}张。"

    user_key = (chat_id, user_id)
    user_records = photo_rate_user[user_key]
    _trim_rate_window(user_records, current_time, window_seconds)
    if len(user_records) >= user_limit:
        return f"当前用户图片发送太快，{window_seconds}秒内最多处理{user_limit}张。"

    chat_records.append(current_time)
    user_records.append(current_time)
    return None


async def warn_photo_rate_limited(message, key: tuple[str, int], text: str, *, window_seconds: int) -> None:
    now = time.time()
    if now - photo_rate_warned_at.get(key, 0) < window_seconds:
        return
    photo_rate_warned_at[key] = now
    await message.reply_text(text)
def batch_capacity_reached(current_count: int, maximum_images: int) -> bool:
    """判断批次是否达到显式硬上限；0 表示仅使用并发和频率限制。"""
    return maximum_images > 0 and current_count >= maximum_images
