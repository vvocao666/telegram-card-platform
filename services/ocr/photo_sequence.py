from __future__ import annotations

import asyncio

from telegram import Update


photo_sequence_by_update: dict[int, int] = {}
_photo_sequence_lock = asyncio.Lock()
_global_photo_sequence = 0


async def assign_photo_sequence(update: Update) -> int:
    global _global_photo_sequence
    key = id(update)
    async with _photo_sequence_lock:
        existing = photo_sequence_by_update.get(key)
        if existing is not None:
            return existing
        _global_photo_sequence += 1
        photo_sequence_by_update[key] = _global_photo_sequence
        return _global_photo_sequence


def photo_sequence(update: Update) -> int:
    return photo_sequence_by_update.get(id(update), 0)


def photo_display_order(update: Update) -> tuple[int, int]:
    message = getattr(update, "message", None)
    message_id = getattr(message, "message_id", None)
    if isinstance(message_id, int):
        return message_id, photo_sequence(update)
    return 10**12, photo_sequence(update)


def forget_photo_sequences(updates: list[Update]) -> None:
    for update in updates:
        photo_sequence_by_update.pop(id(update), None)
