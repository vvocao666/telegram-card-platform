from __future__ import annotations

from services.runtime import reply_html_chunks, send_html_chunks


def safe_chat_title(chat) -> str:
    return getattr(chat, "title", "") or getattr(chat, "full_name", "") or str(getattr(chat, "id", ""))
