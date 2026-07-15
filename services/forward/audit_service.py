from __future__ import annotations

import html
import logging
import tempfile
from pathlib import Path
from collections.abc import Awaitable, Callable

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from utils.text_utils import split_html_message


logger = logging.getLogger("telegram-card-platform")


def user_label(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "Unknown user"
    parts: list[str] = []
    if user.username:
        parts.append(f"@{user.username}")
    name = " ".join(part for part in [user.first_name, user.last_name] if part)
    if name:
        parts.append(name)
    return " | ".join(parts) or "未知用户"


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
    chat = update.effective_chat
    source = html.escape(chat_label(update))
    link = _source_message_link(update)
    if chat and getattr(chat, "type", "") != "private" and link:
        title = getattr(chat, "title", "") or getattr(chat, "full_name", "") or "未命名群组"
        source = f'群组（<a href="{html.escape(link, quote=True)}">{html.escape(title)}</a>）'
    return f"来源: {source}\n发送用户: {html.escape(user_label(update))}"


def _source_message_link(update: Update) -> str:
    chat = update.effective_chat
    message = getattr(update, "effective_message", None) or getattr(update, "message", None)
    message_id = int(getattr(message, "message_id", 0) or 0) if message else 0
    if not chat or message_id <= 0 or getattr(chat, "type", "") == "private":
        return ""
    username = str(getattr(chat, "username", "") or "").lstrip("@")
    if username:
        return f"https://t.me/{username}/{message_id}"
    chat_id = str(getattr(chat, "id", ""))
    if chat_id.startswith("-100") and chat_id[4:].isdigit():
        return f"https://t.me/c/{chat_id[4:]}/{message_id}"
    return ""


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


async def send_audit_bot_message(
    chat_id: int,
    text: str,
    *,
    bot_token: str,
    timeout: float,
) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=timeout) as client:
        for chunk in split_html_message(text):
            response = await client.post(
                url,
                data={
                    "chat_id": str(chat_id),
                    "text": chunk,
                    "parse_mode": ParseMode.HTML,
                    "disable_web_page_preview": "true",
                },
            )
            response.raise_for_status()


async def send_audit_bot_photos(
    chat_id: int,
    photo_paths: list[Path],
    caption_text: str,
    *,
    bot_token: str,
    timeout: float,
    send_message: Callable[[int, str], Awaitable[None]],
) -> None:
    photo_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    caption_chunks = split_html_message(caption_text, limit=900)
    first_caption = caption_chunks[0] if caption_chunks else ""
    async with httpx.AsyncClient(timeout=timeout) as client:
        for index, photo_path in enumerate(photo_paths):
            data = {"chat_id": str(chat_id)}
            if index == 0 and first_caption:
                data["caption"] = first_caption
                data["parse_mode"] = ParseMode.HTML
            with photo_path.open("rb") as photo_file:
                response = await client.post(
                    photo_url,
                    data=data,
                    files={"photo": (photo_path.name, photo_file, "image/jpeg")},
                )
            response.raise_for_status()
    for extra_chunk in caption_chunks[1:]:
        await send_message(chat_id, extra_chunk)
