from __future__ import annotations

from telegram.constants import ParseMode

from utils.text_utils import split_html_message


async def reply_html_chunks(message, text: str, **kwargs) -> None:
    chunks = split_html_message(text)
    for index, chunk in enumerate(chunks):
        await message.reply_text(
            chunk,
            parse_mode=ParseMode.HTML,
            **(kwargs if index == 0 else {}),
        )


async def send_html_chunks(context, chat_id: int, text: str) -> None:
    for chunk in split_html_message(text):
        await context.bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


def safe_chat_title(chat) -> str:
    return getattr(chat, "title", "") or getattr(chat, "full_name", "") or str(getattr(chat, "id", ""))
