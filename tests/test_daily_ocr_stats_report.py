from __future__ import annotations

import asyncio
from datetime import date
import json
from pathlib import Path

from services.ocr.daily_stats_report import (
    collect_daily_ocr_stats,
    format_chat_daily_ocr_stats,
    format_daily_ocr_stats,
    send_daily_ocr_stats,
)


def _write_record(
    root: Path,
    report_date: date,
    name: str,
    *,
    chat_id: int,
    chat_title: str,
    user_id: int,
    username: str,
    pubg: list[str],
    psn: list[str],
) -> None:
    record_dir = root / report_date.isoformat() / name
    record_dir.mkdir(parents=True)
    (record_dir / "record.json").write_text(
        json.dumps(
            {
                "source": {
                    "chat_id": chat_id,
                    "chat_title": chat_title,
                    "user_id": user_id,
                    "username": username,
                },
                "final_cards": pubg,
                "final_psn_cards": psn,
                "status": "complete",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_daily_stats_group_by_chat_and_user_and_dedupe_per_image(tmp_path: Path):
    report_date = date(2026, 7, 13)
    _write_record(
        tmp_path,
        report_date,
        "001-one",
        chat_id=-1001,
        chat_title="群<A>",
        user_id=10,
        username="alice",
        pubg=["S07336-AAAA-BBBB-CCCCC", "S07336-AAAA-BBBB-CCCCC"],
        psn=[],
    )
    _write_record(
        tmp_path,
        report_date,
        "002-two",
        chat_id=-1001,
        chat_title="群<A>",
        user_id=10,
        username="alice",
        pubg=["S07336-DDDD-EEEE-FFFFF"],
        psn=["AAAA-BBBB-CCCC"],
    )
    _write_record(
        tmp_path,
        report_date,
        "003-three",
        chat_id=-1001,
        chat_title="群<A>",
        user_id=20,
        username="bob",
        pubg=[],
        psn=["DDDD-EEEE-FFFF"],
    )
    _write_record(
        tmp_path,
        report_date,
        "004-four",
        chat_id=-1001,
        chat_title="群<A>",
        user_id=20,
        username="bob",
        pubg=["S07336-AAAA-BBBB-CCCCC"],
        psn=["AAAA-BBBB-CCCC"],
    )

    stats = collect_daily_ocr_stats(tmp_path, report_date)

    assert stats.images == 4
    assert stats.pubg_cards == 2
    assert stats.psn_cards == 2
    assert stats.cards == 4
    assert len(stats.sources) == 2
    alice = next(row for row in stats.sources if row.username == "alice")
    assert (alice.images, alice.pubg_cards, alice.psn_cards) == (2, 2, 1)
    message = "\n".join(format_daily_ocr_stats(stats))
    assert message.count("群：群&lt;A&gt;") == 1
    assert "用户：@alice" in message
    assert "用户：@bob" in message
    assert "卡密合计：4 个" in message

    group_message = "\n".join(format_chat_daily_ocr_stats(stats, -1001))
    assert group_message.startswith("今日识别卡密统计如下：")
    assert group_message.count("用户：@alice") == 1
    assert "PUBG：【 <b>2</b> 】" in group_message
    assert "P S N：【 <b>1</b> 】" in group_message
    assert "合计发送图片：2张" in group_message
    assert group_message.count("用户：@bob") == 1
    assert "合计发送图片：2张" in group_message


def test_daily_stats_duplicate_cards_count_only_the_first_occurrence(tmp_path: Path):
    report_date = date(2026, 7, 13)
    duplicate = "S07336-AAAA-BBBB-CCCCC"
    _write_record(
        tmp_path,
        report_date,
        "001-first",
        chat_id=-1001,
        chat_title="目标群",
        user_id=10,
        username="alice",
        pubg=[duplicate],
        psn=[],
    )
    _write_record(
        tmp_path,
        report_date,
        "002-duplicate",
        chat_id=-1001,
        chat_title="目标群",
        user_id=20,
        username="bob",
        pubg=[duplicate],
        psn=[],
    )

    stats = collect_daily_ocr_stats(tmp_path, report_date)
    alice = next(row for row in stats.sources if row.username == "alice")
    bob = next(row for row in stats.sources if row.username == "bob")

    assert stats.images == 2
    assert stats.pubg_cards == 1
    assert (alice.images, alice.pubg_cards) == (1, 1)
    assert (bob.images, bob.pubg_cards) == (1, 0)


def test_chat_daily_stats_excludes_other_chats_and_includes_users_with_images(tmp_path: Path):
    report_date = date(2026, 7, 13)
    _write_record(
        tmp_path,
        report_date,
        "target",
        chat_id=-1001,
        chat_title="目标群",
        user_id=10,
        username="alice",
        pubg=["S07336-AAAA-BBBB-CCCCC"],
        psn=[],
    )
    _write_record(
        tmp_path,
        report_date,
        "empty",
        chat_id=-1001,
        chat_title="目标群",
        user_id=20,
        username="bob",
        pubg=[],
        psn=[],
    )
    _write_record(
        tmp_path,
        report_date,
        "other",
        chat_id=-2002,
        chat_title="其他群",
        user_id=30,
        username="carol",
        pubg=["S07336-DDDD-EEEE-FFFFF"],
        psn=[],
    )

    stats = collect_daily_ocr_stats(tmp_path, report_date)
    message = "\n".join(format_chat_daily_ocr_stats(stats, -1001))

    assert "用户：@alice" in message
    assert "用户：@bob" in message
    assert "PUBG：【 <b>0</b> 】" in message
    assert "P S N：【 <b>0</b> 】" in message
    assert message.count("合计发送图片：1张") == 2
    assert "用户：@carol" not in message


def test_chat_daily_stats_excludes_only_the_configured_bot_owner(tmp_path: Path):
    report_date = date(2026, 7, 13)
    _write_record(
        tmp_path,
        report_date,
        "ordinary",
        chat_id=-1001,
        chat_title="目标群",
        user_id=10,
        username="ordinary",
        pubg=["S07336-AAAA-BBBB-CCCCC"],
        psn=[],
    )
    _write_record(
        tmp_path,
        report_date,
        "owner",
        chat_id=-1001,
        chat_title="目标群",
        user_id=20,
        username="owner",
        pubg=["S07336-DDDD-EEEE-FFFFF"],
        psn=[],
    )

    stats = collect_daily_ocr_stats(tmp_path, report_date)
    message = "\n".join(format_chat_daily_ocr_stats(stats, -1001, excluded_user_ids={20}))

    assert "用户：@ordinary" in message
    assert "合计发送图片：1张" in message
    assert "用户：@owner" not in message


def test_excluded_owner_cards_do_not_consume_first_occurrence(tmp_path: Path):
    report_date = date(2026, 7, 13)
    duplicate = "S07336-AAAA-BBBB-CCCCC"
    _write_record(
        tmp_path,
        report_date,
        "001-owner",
        chat_id=-1001,
        chat_title="目标群",
        user_id=20,
        username="owner",
        pubg=[duplicate],
        psn=[],
    )
    _write_record(
        tmp_path,
        report_date,
        "002-ordinary",
        chat_id=-1001,
        chat_title="目标群",
        user_id=10,
        username="ordinary",
        pubg=[duplicate],
        psn=[],
    )

    stats = collect_daily_ocr_stats(tmp_path, report_date, excluded_user_ids={20})

    assert stats.images == 1
    assert stats.pubg_cards == 1
    assert [row.username for row in stats.sources] == ["ordinary"]


def test_daily_stats_counts_failed_or_empty_image_without_inventing_cards(tmp_path: Path):
    report_date = date(2026, 7, 13)
    _write_record(
        tmp_path,
        report_date,
        "empty",
        chat_id=10,
        chat_title="",
        user_id=99,
        username="",
        pubg=[],
        psn=[],
    )

    stats = collect_daily_ocr_stats(tmp_path, report_date)

    assert stats.images == 1
    assert stats.cards == 0
    message = "\n".join(format_daily_ocr_stats(stats))
    assert "群：私聊" in message
    assert "用户：用户ID 99" in message


def test_daily_stats_send_once_and_persist_state(tmp_path: Path):
    class Bot:
        def __init__(self):
            self.messages = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

    async def scenario():
        report_date = date(2026, 7, 13)
        audit_root = tmp_path / "audit"
        state_path = tmp_path / "state.json"
        _write_record(
            audit_root,
            report_date,
            "one",
            chat_id=-1001,
            chat_title="测试群",
            user_id=10,
            username="alice",
            pubg=["S07336-AAAA-BBBB-CCCCC"],
            psn=[],
        )
        bot = Bot()
        first = await send_daily_ocr_stats(
            bot,
            123,
            audit_root=audit_root,
            state_path=state_path,
            report_date=report_date,
        )
        second = await send_daily_ocr_stats(
            bot,
            123,
            audit_root=audit_root,
            state_path=state_path,
            report_date=report_date,
        )
        assert first is True
        assert second is False
        assert len(bot.messages) == 1
        assert bot.messages[0]["chat_id"] == 123
        assert bot.messages[0]["parse_mode"] == "HTML"
        assert json.loads(state_path.read_text(encoding="utf-8"))["last_sent_date"] == "2026-07-13"

    asyncio.run(scenario())


def test_daily_stats_report_chunks_large_source_list():
    from services.ocr.daily_stats_report import DailyOcrStats, OcrSourceStats

    sources = tuple(
        OcrSourceStats(
            chat_id=index,
            chat_title=f"群{index}" + "长" * 80,
            user_id=index,
            username=f"user_{index}",
            images=1,
            pubg_cards=1,
            psn_cards=0,
        )
        for index in range(60)
    )
    messages = format_daily_ocr_stats(
        DailyOcrStats(
            report_date=date(2026, 7, 13),
            sources=sources,
            images=60,
            pubg_cards=60,
            psn_cards=0,
        )
    )

    assert len(messages) > 1
    assert all(len(message) <= 3900 for message in messages)
    assert "卡密合计：60 个" in messages[-1]
