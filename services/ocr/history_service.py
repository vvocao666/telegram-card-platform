from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Callable


@dataclass(frozen=True)
class CardHistoryDuplicate:
    card_type: str
    card: str
    first_seen_at: str
    first_source_user: str


@dataclass(frozen=True)
class CardHistoryHooks:
    store: Any
    ledger_timezone: tzinfo
    fuzzy_suffix: str
    result_card_lines: Callable[[list[Any]], tuple[list[str], list[str]]]
    user_label: Callable[[Any], str]
    format_card: Callable[[str], str]


def card_history_day_key(
    chat_id: int,
    hooks: CardHistoryHooks,
    now: datetime | None = None,
) -> str:
    reset_hour = hooks.store.get_ledger_reset_hour(chat_id)
    local_now = (now or datetime.now(hooks.ledger_timezone)).astimezone(hooks.ledger_timezone)
    day = local_now.date()
    if local_now.hour < reset_hour:
        day -= timedelta(days=1)
    return day.isoformat()


def format_history_time(created_at: str, ledger_timezone: tzinfo) -> str:
    parsed = datetime.fromisoformat(created_at)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ledger_timezone).strftime("%H:%M:%S")


def register_card_history(
    updates: list[Any],
    results: list[Any],
    hooks: CardHistoryHooks,
) -> list[CardHistoryDuplicate]:
    if not updates:
        return []
    chat = updates[-1].effective_chat
    if not chat:
        return []
    chat_id = chat.id
    day_key = card_history_day_key(chat_id, hooks)
    hooks.store.clear_recognized_cards_before(day_key)
    duplicates: list[CardHistoryDuplicate] = []
    seen_reported: set[tuple[str, str]] = set()
    for update, result in zip(updates, results):
        source_user = hooks.user_label(update)
        source_message_id = update.message.message_id if update.message else None
        pubg_cards, psn_lines = hooks.result_card_lines([result])
        typed_cards = (
            ("PUBG", pubg_cards),
            ("PSN", [card for card in psn_lines if not card.endswith(hooks.fuzzy_suffix)]),
        )
        for card_type, cards in typed_cards:
            for card in cards:
                record = hooks.store.record_recognized_card(
                    chat_id=chat_id,
                    card_type=card_type,
                    card=card,
                    day_key=day_key,
                    source_user=source_user,
                    source_message_id=source_message_id,
                )
                key = (card_type, card)
                if record is None or key in seen_reported:
                    continue
                seen_reported.add(key)
                duplicates.append(
                    CardHistoryDuplicate(
                        card_type=card_type,
                        card=card,
                        first_seen_at=record.created_at,
                        first_source_user=record.source_user,
                    )
                )
    return duplicates


def source_username_only(source_user: str) -> str:
    match = re.search(r"@[A-Za-z0-9_]+", source_user)
    if match:
        return match.group(0)
    parts = [part.strip() for part in source_user.split("|") if part.strip()]
    return parts[0] if parts else source_user.strip() or "Unknown"


def append_history_duplicates(
    reply: str,
    duplicates: list[CardHistoryDuplicate],
    hooks: CardHistoryHooks,
) -> str:
    if not duplicates:
        return reply
    lines = ["<b>⚠️今日重复出现卡密⚠️</b>"]
    for duplicate in duplicates:
        source_user = html.escape(source_username_only(duplicate.first_source_user))
        lines.extend(
            [
                f"{duplicate.card_type}：{hooks.format_card(duplicate.card)}",
                "<b>——————出现时间——————</b>",
                f"首次 {format_history_time(duplicate.first_seen_at, hooks.ledger_timezone)} 来自 | {source_user} |",
            ]
        )
    return reply + "\n\n" + "\n".join(lines)
