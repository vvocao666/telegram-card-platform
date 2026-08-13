from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import html
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable


SHANGHAI_TZ = timezone(timedelta(hours=8))
DEFAULT_STATE_PATH = Path("outputs/daily_ocr_stats_state.json")
TELEGRAM_MESSAGE_LIMIT = 3900


@dataclass(frozen=True)
class OcrSourceStats:
    chat_id: int
    chat_title: str
    user_id: int
    username: str
    images: int
    pubg_cards: int
    psn_cards: int

    @property
    def cards(self) -> int:
        return self.pubg_cards + self.psn_cards


@dataclass(frozen=True)
class DailyOcrStats:
    report_date: date
    sources: tuple[OcrSourceStats, ...]
    images: int
    pubg_cards: int
    psn_cards: int

    @property
    def cards(self) -> int:
        return self.pubg_cards + self.psn_cards


@dataclass(frozen=True)
class OcrStatsTimeRange:
    start_at: datetime
    end_at: datetime


class OcrStatsTimeRangeError(ValueError):
    pass


def parse_ocr_stats_time_range(command_text: str, command_time: datetime) -> OcrStatsTimeRange:
    """Parse /统计, /统计HH:MM, or /统计HH:MM-HH:MM in Beijing time."""
    current = _as_shanghai(command_time)
    text = str(command_text or "").strip()
    if not text.startswith("/统计"):
        raise OcrStatsTimeRangeError("时间格式错误，请使用：/统计、/统计12:01 或 /统计12:00-18:00")
    argument = text[len("/统计") :].strip()
    if argument.startswith("@"):
        _bot_name, separator, remainder = argument.partition(" ")
        argument = remainder.strip() if separator else ""

    midnight = datetime.combine(current.date(), time.min, SHANGHAI_TZ)
    if not argument:
        return OcrStatsTimeRange(midnight, current)

    parts = argument.split("-")
    if len(parts) == 1:
        start_at = _parse_clock_time(parts[0], current.date())
        end_at = current
    elif len(parts) == 2:
        start_at = _parse_clock_time(parts[0], current.date())
        end_at = _parse_clock_time(parts[1], current.date())
    else:
        raise OcrStatsTimeRangeError("时间格式错误，请使用：/统计、/统计12:01 或 /统计12:00-18:00")

    if start_at > current:
        raise OcrStatsTimeRangeError("开始时间不能晚于命令发送时间。")
    if end_at > current:
        raise OcrStatsTimeRangeError("结束时间不能晚于命令发送时间。")
    if end_at <= start_at:
        raise OcrStatsTimeRangeError("结束时间必须晚于开始时间。")
    return OcrStatsTimeRange(start_at, end_at)


def collect_daily_ocr_stats(
    audit_root: Path,
    report_date: date,
    *,
    excluded_user_ids: set[int] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> DailyOcrStats:
    """按群和用户汇总指定北京时间自然日的 OCR 审计记录。"""
    grouped: dict[tuple[int, int], dict[str, object]] = {}
    excluded = excluded_user_ids or set()
    seen_pubg: set[str] = set()
    seen_psn: set[str] = set()
    seen_images: set[tuple[str, ...]] = set()
    date_root = audit_root / report_date.isoformat()
    for record_path in sorted(date_root.glob("*/record.json")) if date_root.exists() else ():
        record = _read_json(record_path)
        if not record:
            continue
        if start_at is not None or end_at is not None:
            created_at = _record_created_at(record, record_path, report_date)
            if created_at is None:
                continue
            if start_at is not None and created_at < _as_shanghai(start_at):
                continue
            if end_at is not None and created_at > _as_shanghai(end_at):
                continue
        source = record.get("source")
        source = source if isinstance(source, dict) else {}
        chat_id = _safe_int(source.get("chat_id"))
        user_id = _safe_int(source.get("user_id"))
        if user_id in excluded:
            continue
        image_key = _record_image_key(record, record_path, chat_id)
        if image_key in seen_images:
            continue
        seen_images.add(image_key)
        key = (chat_id, user_id)
        row = grouped.setdefault(
            key,
            {
                "chat_id": chat_id,
                "chat_title": str(source.get("chat_title", "") or ""),
                "user_id": user_id,
                "username": str(source.get("username", "") or ""),
                "images": 0,
                "pubg_cards": 0,
                "psn_cards": 0,
            },
        )
        row["images"] = int(row["images"]) + 1
        pubg_cards = _new_cards(record.get("final_cards"), seen_pubg)
        psn_cards = _new_cards(record.get("final_psn_cards"), seen_psn)
        row["pubg_cards"] = int(row["pubg_cards"]) + len(pubg_cards)
        row["psn_cards"] = int(row["psn_cards"]) + len(psn_cards)

    sources = tuple(
        OcrSourceStats(**row)
        for row in sorted(
            grouped.values(),
            key=lambda value: (
                str(value["chat_title"]).casefold(),
                str(value["username"]).casefold(),
                int(value["chat_id"]),
                int(value["user_id"]),
            ),
        )
    )
    return DailyOcrStats(
        report_date=report_date,
        sources=sources,
        images=sum(row.images for row in sources),
        pubg_cards=sum(row.pubg_cards for row in sources),
        psn_cards=sum(row.psn_cards for row in sources),
    )


def format_daily_ocr_stats(stats: DailyOcrStats) -> list[str]:
    """生成不会超过 Telegram 限制的 HTML 报告分段。"""
    header = [
        "📊 <b>每日卡密识别统计</b>",
        f"日期：{stats.report_date.isoformat()}",
        "",
    ]
    blocks = _format_source_groups(stats.sources)
    if not blocks:
        blocks.append("当日未收到 OCR 图片。")
    footer = "\n".join(
        (
            "━━━━━━━━━━━━",
            f"图片合计：{stats.images} 张",
            f"PUBG：{stats.pubg_cards} 个",
            f"PSN：{stats.psn_cards} 个",
            f"卡密合计：{stats.cards} 个",
        )
    )
    return _chunk_report(header, blocks, footer)


def format_chat_daily_ocr_stats(
    stats: DailyOcrStats,
    chat_id: int,
    *,
    excluded_user_ids: set[int] | None = None,
) -> list[str]:
    """按用户生成当前群当天的图片与卡密统计，不包含其他群。"""
    excluded = excluded_user_ids or set()
    sources = tuple(
        source
        for source in stats.sources
        if source.chat_id == chat_id and source.images > 0 and source.user_id not in excluded
    )
    if not sources:
        return ["今日暂无卡密识别记录。"]

    blocks: list[str] = []
    for source in sources:
        user_label = (
            f"@{html.escape(source.username.lstrip('@'))}"
            if source.username
            else (f"用户ID {source.user_id}" if source.user_id else "未知用户")
        )
        blocks.append(
            "\n".join(
                (
                    f"用户：{user_label}",
                    f"PUBG：【 <b>{source.pubg_cards}</b> 】",
                    f"P S N：【 <b>{source.psn_cards}</b> 】",
                    f"合计发送图片：{source.images}张",
                )
            )
        )
    return [message.rstrip() for message in _chunk_report(["今日识别卡密统计如下：", ""], blocks, "")]


def _format_source_groups(sources: tuple[OcrSourceStats, ...]) -> list[str]:
    grouped: dict[int, list[OcrSourceStats]] = {}
    for source in sources:
        grouped.setdefault(source.chat_id, []).append(source)

    blocks: list[str] = []
    for group_sources in grouped.values():
        first = group_sources[0]
        chat_label = (
            html.escape(first.chat_title)
            if first.chat_title
            else (f"群ID {first.chat_id}" if first.chat_id < 0 else "私聊")
        )
        user_blocks: list[str] = []
        for source in group_sources:
            user_label = (
                f"@{html.escape(source.username.lstrip('@'))}"
                if source.username
                else (f"用户ID {source.user_id}" if source.user_id else "未知用户")
            )
            user_blocks.append(
                "\n".join(
                    (
                        f"用户：{user_label}",
                        f"图片：{source.images} 张",
                        f"卡密：{source.cards} 个（PUBG {source.pubg_cards} / PSN {source.psn_cards}）",
                    )
                )
            )
        blocks.append(f"群：{chat_label}\n" + "\n\n".join(user_blocks))
    return blocks


async def send_daily_ocr_stats(
    bot: Any,
    owner_chat_id: int,
    *,
    audit_root: Path,
    state_path: Path,
    report_date: date,
) -> bool:
    """发送一次指定日期报告；成功后持久化日期，避免重启重复发送。"""
    if owner_chat_id == 0 or _last_sent_date(state_path) == report_date:
        return False
    stats = await asyncio.to_thread(collect_daily_ocr_stats, audit_root, report_date)
    for message in format_daily_ocr_stats(stats):
        await bot.send_message(chat_id=owner_chat_id, text=message, parse_mode="HTML")
    await asyncio.to_thread(_write_state, state_path, report_date)
    return True


async def daily_ocr_stats_loop(
    bot: Any,
    owner_chat_id: int,
    *,
    audit_root: Path,
    state_path: Path = DEFAULT_STATE_PATH,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    logger: logging.Logger | None = None,
) -> None:
    """北京时间零点发送上一自然日统计，并补发服务离线期间错过的报告。"""
    clock = now or (lambda: datetime.now(SHANGHAI_TZ))
    current = _as_shanghai(clock())
    if not state_path.exists():
        await asyncio.to_thread(_write_state, state_path, current.date() - timedelta(days=1))
    while True:
        current = _as_shanghai(clock())
        report_date = current.date() - timedelta(days=1)
        delivery_failed = False
        try:
            await send_daily_ocr_stats(
                bot,
                owner_chat_id,
                audit_root=audit_root,
                state_path=state_path,
                report_date=report_date,
            )
        except Exception:
            delivery_failed = True
            if logger is not None:
                logger.exception("Daily OCR statistics delivery failed")
        if delivery_failed:
            await sleep(300.0)
            continue
        next_midnight = datetime.combine(current.date() + timedelta(days=1), time.min, SHANGHAI_TZ)
        await sleep(max((next_midnight - current).total_seconds(), 1.0))


def _chunk_report(header: list[str], blocks: list[str], footer: str) -> list[str]:
    chunks: list[str] = []
    current = "\n".join(header).rstrip()
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= TELEGRAM_MESSAGE_LIMIT:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = block
    candidate = f"{current}\n\n{footer}" if current else footer
    if len(candidate) <= TELEGRAM_MESSAGE_LIMIT:
        chunks.append(candidate)
    else:
        if current:
            chunks.append(current)
        chunks.append(footer)
    return chunks


def _stable_cards(value: object) -> list[str]:
    values = value if isinstance(value, list) else []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        card = str(item).strip().upper()
        if card and card not in seen:
            seen.add(card)
            result.append(card)
    return result


def _new_cards(value: object, seen: set[str]) -> list[str]:
    """按审计顺序保留当天第一次出现的卡密。"""
    result: list[str] = []
    for card in _stable_cards(value):
        if card in seen:
            continue
        seen.add(card)
        result.append(card)
    return result


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_clock_time(value: str, report_date: date) -> datetime:
    try:
        parsed = datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError as exc:
        raise OcrStatsTimeRangeError(
            "时间格式错误，请使用：/统计、/统计12:01 或 /统计12:00-18:00"
        ) from exc
    return datetime.combine(report_date, parsed, SHANGHAI_TZ)


def _record_created_at(record: dict[str, object], record_path: Path, report_date: date) -> datetime | None:
    for field_name in ("message_created_at", "created_at"):
        value = str(record.get(field_name, "") or "").strip()
        if value:
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI_TZ)
            except ValueError:
                pass
    folder_time = record_path.parent.name.split("_", 1)[0]
    if len(folder_time) == 6 and folder_time.isdigit():
        try:
            parsed = datetime.strptime(folder_time, "%H%M%S").time()
        except ValueError:
            return None
        return datetime.combine(report_date, parsed, SHANGHAI_TZ)
    return None


def _record_image_key(record: dict[str, object], record_path: Path, chat_id: int) -> tuple[str, ...]:
    """新记录按 Telegram 消息去重；没有消息标识的旧记录保持逐条计数。"""
    message_id = _safe_int(record.get("message_id"))
    file_unique_id = str(record.get("file_unique_id", "") or "").strip()
    if message_id or file_unique_id:
        return ("telegram", str(chat_id), str(message_id), file_unique_id)
    return ("legacy", str(record_path.parent.resolve()))


def _last_sent_date(state_path: Path) -> date | None:
    value = str(_read_json(state_path).get("last_sent_date", ""))
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _write_state(state_path: Path, report_date: date) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"last_sent_date": report_date.isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(state_path)


def _as_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)
