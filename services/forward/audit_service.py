from __future__ import annotations

import html
import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes


logger = logging.getLogger("telegram-card-platform")


def user_label(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "Unknown user"
    parts = [str(user.id)]
    if user.username:
        parts.append(f"@{user.username}")
    name = " ".join(part for part in [user.first_name, user.last_name] if part)
    if name:
        parts.append(name)
    return " | ".join(parts)


def chat_label(update: Update | None) -> str:
    chat = update.effective_chat if update else None
    if not chat:
        return "未知"
    chat_type = getattr(chat, "type", "")
    if chat_type == "private":
        return "私聊"
    title = getattr(chat, "title", "") or getattr(chat, "full_name", "") or "未命名群组"
    return f"群组（{title}）"


def audit_source_text(update: Update | None) -> str:
    if not update:
        return "来源: Unknown\n发送用户: Unknown"
    return f"来源: {html.escape(chat_label(update))}\n发送用户: {html.escape(user_label(update))}"


def audit_photo_file_ids(updates: list[Update]) -> list[str]:
    file_ids: list[str] = []
    seen: set[str] = set()
    for update in updates:
        message = getattr(update, "message", None)
        photos = getattr(message, "photo", None)
        if not photos:
            continue
        file_id = getattr(photos[-1], "file_id", "")
        if file_id and file_id not in seen:
            seen.add(file_id)
            file_ids.append(file_id)
    return file_ids


async def download_audit_photo_paths(updates: list[Update], context: ContextTypes.DEFAULT_TYPE) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for update in updates:
        message = getattr(update, "message", None)
        photos = getattr(message, "photo", None)
        if not photos:
            continue
        photo = photos[-1]
        unique_id = getattr(photo, "file_unique_id", "") or getattr(photo, "file_id", "")
        if unique_id in seen:
            continue
        seen.add(unique_id)
        tg_file = await context.bot.get_file(photo.file_id)
        temp_dir = Path(tempfile.mkdtemp(prefix="s07_audit_"))
        image_path = temp_dir / f"{unique_id}.jpg"
        await tg_file.download_to_drive(custom_path=image_path)
        paths.append(image_path)
    return paths


def cleanup_audit_photo_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        except OSError:
            logger.warning("Failed to clean audit photo temp path: %s", path)


def update_is_private_chat(update: Update | None) -> bool:
    if not update or not update.effective_chat:
        return False
    return getattr(update.effective_chat, "type", "") == "private"
