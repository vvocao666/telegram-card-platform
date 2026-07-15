from __future__ import annotations

import asyncio
from types import SimpleNamespace

from handlers.ocr_stats_handler import group_daily_ocr_stats_command


class _Message:
    def __init__(self) -> None:
        self.replies: list[dict[str, object]] = []

    async def reply_text(self, text: str, **kwargs: object) -> None:
        self.replies.append({"text": text, **kwargs})


def test_group_daily_stats_private_chat_is_rejected():
    async def scenario() -> None:
        message = _Message()
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=123, type="private"),
        )

        await group_daily_ocr_stats_command(update, SimpleNamespace())

        assert message.replies == [{"text": "该命令仅限群聊使用。"}]

    asyncio.run(scenario())


def test_group_daily_stats_command_is_registered():
    source = open("handlers/registry.py", encoding="utf-8").read()
    assert 'filters.Regex(r"^/统计(?:@\\w+)?\\s*$")' in source
