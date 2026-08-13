from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from handlers.ocr_stats_handler import group_daily_ocr_stats_command


class _Message:
    def __init__(self, text: str = "/统计") -> None:
        self.text = text
        self.date = datetime(2026, 8, 13, 10, 30, tzinfo=timezone.utc)
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
    assert 'filters.Regex(r"^/统计(?:@\\w+)?(?:\\s*[^\\r\\n]*)?$")' in source


def test_group_daily_stats_excludes_only_the_configured_bot_owner(monkeypatch):
    async def scenario() -> None:
        message = _Message()
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=-1001, type="group"),
        )
        stats = SimpleNamespace(
            sources=(
                SimpleNamespace(chat_id=-1001, user_id=10),
                SimpleNamespace(chat_id=-1001, user_id=20),
            )
        )
        captured_collect: dict[str, object] = {}

        def collect_stats(*_args, excluded_user_ids, **_kwargs):
            captured_collect["excluded_user_ids"] = excluded_user_ids
            return stats

        monkeypatch.setattr("handlers.ocr_stats_handler.collect_daily_ocr_stats", collect_stats)
        monkeypatch.setattr("handlers.ocr_stats_handler._owner_user_id", lambda: 20)
        captured: dict[str, object] = {}

        def format_stats(_stats, _chat_id, *, excluded_user_ids):
            captured["excluded_user_ids"] = excluded_user_ids
            return ["统计结果"]

        monkeypatch.setattr("handlers.ocr_stats_handler.format_chat_daily_ocr_stats", format_stats)

        await group_daily_ocr_stats_command(update, SimpleNamespace())

        assert captured["excluded_user_ids"] == {20}
        assert captured_collect["excluded_user_ids"] == {20}
        assert message.replies == [{"text": "统计结果", "parse_mode": "HTML"}]

    asyncio.run(scenario())


def test_group_daily_stats_passes_custom_time_range(monkeypatch):
    async def scenario() -> None:
        message = _Message("/统计12:01")
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=-1001, type="group"),
        )
        captured: dict[str, object] = {}

        def collect_stats(*_args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(sources=())

        monkeypatch.setattr("handlers.ocr_stats_handler.collect_daily_ocr_stats", collect_stats)
        monkeypatch.setattr("handlers.ocr_stats_handler._owner_user_id", lambda: None)
        monkeypatch.setattr(
            "handlers.ocr_stats_handler.format_chat_daily_ocr_stats",
            lambda *_args, **_kwargs: ["统计结果"],
        )

        await group_daily_ocr_stats_command(update, SimpleNamespace())

        assert captured["start_at"].strftime("%Y-%m-%d %H:%M") == "2026-08-13 12:01"
        assert captured["end_at"].strftime("%Y-%m-%d %H:%M") == "2026-08-13 18:30"
        assert message.replies == [{"text": "统计结果", "parse_mode": "HTML"}]

    asyncio.run(scenario())


def test_group_daily_stats_rejects_invalid_time(monkeypatch):
    async def scenario() -> None:
        message = _Message("/统计25:00")
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=-1001, type="group"),
        )

        await group_daily_ocr_stats_command(update, SimpleNamespace())

        assert "时间格式错误" in str(message.replies[0]["text"])

    asyncio.run(scenario())
