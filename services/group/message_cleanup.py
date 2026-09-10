from __future__ import annotations

import asyncio
from datetime import timedelta

from telegram.error import BadRequest, RetryAfter


def can_delete_group_messages(member, chat_type: str) -> bool:
    return member.status == "creator" or (
        member.status == "administrator"
        and (chat_type == "group" or member.can_delete_messages is True)
    )


async def delete_message_range(bot, chat_id: int, chat_type: str, first_id: int, last_id: int) -> None:
    """Telegram enforces the 48-hour limit; never infer message age from a failed ID."""
    async def delete_batch(ids: list[int]) -> None:
        while True:
            try:
                await bot.delete_messages(chat_id=chat_id, message_ids=ids)
                break
            except RetryAfter as exc:
                delay = exc.retry_after
                await asyncio.sleep(delay.total_seconds() if isinstance(delay, timedelta) else delay)
            except BadRequest as exc:
                if str(exc).lower() not in {
                    "message can't be deleted",
                    "message to delete not found",
                    "message_id_invalid",
                }:
                    raise
                member = await bot.get_chat_member(chat_id, bot.id)
                if not can_delete_group_messages(member, chat_type):
                    raise BadRequest("Bot lost delete permission") from exc
                if len(ids) > 1:
                    middle = len(ids) // 2
                    await delete_batch(ids[:middle])
                    await delete_batch(ids[middle:])
                break
        await asyncio.sleep(0.05)

    # ponytail: without a history API, the first pass scans IDs; completed passes
    # can be skipped by the caller. Do not stop on gaps or undeletable service messages.
    for end in range(last_id, first_id - 1, -100):
        await delete_batch(list(range(end, max(first_id - 1, end - 100), -1)))
