from __future__ import annotations

import html
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from services.ocr.pubg_candidate_merge import compact_card, hamming_distance
from services.ocr.source_consensus import PUBG_CARD_RE, repeated_pubg_source_consensus


@dataclass(frozen=True)
class ManualReviewItem:
    """一张需要人工核对的原图，绝不包含未经确认的卡密文本。"""

    batch_index: int
    reason: str


class ManualReviewNotifier:
    """在原聊天、原图片位置发送一次性核对提醒。"""

    def __init__(self, *, ttl_seconds: int = 24 * 60 * 60, capacity: int = 5000) -> None:
        self._ttl_seconds = ttl_seconds
        self._capacity = capacity
        self._sent: OrderedDict[str, float] = OrderedDict()

    def needs_review(self, result: Any) -> ManualReviewItem | None:
        expected = max(result.pubg_expected_count or 0, result.psn_expected_count or 0)
        actual = len(result.cards) + len(result.psn_cards)
        if expected <= 1 and (
            repeated_pubg_source_consensus(result)
            or _has_dominant_repeated_pubg_evidence(result)
        ):
            return None
        if result.has_unresolved_pubg_fragment:
            return ManualReviewItem(0, "存在无法按相邻行完整重建的卡密")
        if expected and actual < expected:
            return ManualReviewItem(0, "识别数量少于图片中的卡密标记")
        if result.uncertain_count and not _has_repeated_exact_pubg_evidence(result):
            return ManualReviewItem(0, "识别结果存在冲突，无法安全确认")
        return None

    async def notify(
        self,
        update: Any,
        context: Any,
        *,
        batch_index: int,
        item: ManualReviewItem,
    ) -> bool:
        message = getattr(update, "message", None)
        chat = getattr(message, "chat", None)
        photos = getattr(message, "photo", None) or []
        if message is None or chat is None or not photos:
            return False
        photo = photos[-1]
        key = f"{getattr(chat, 'id', '')}:{getattr(message, 'message_id', '')}:{getattr(photo, 'file_unique_id', '')}"
        if self._already_sent(key):
            return False
        text = (
            f"本批第 {batch_index} 张图片识别结果无法确认，请人工核对。\n"
            f"原因：{html.escape(item.reason)}"
        )
        try:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo.file_id,
                caption=text,
                reply_to_message_id=message.message_id,
            )
        except Exception:
            return False
        self._mark_sent(key)
        return True

    def _already_sent(self, key: str) -> bool:
        self._cleanup()
        return key in self._sent

    def _mark_sent(self, key: str) -> None:
        self._cleanup()
        self._sent[key] = time.monotonic() + self._ttl_seconds
        self._sent.move_to_end(key)
        while len(self._sent) > self._capacity:
            self._sent.popitem(last=False)

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [key for key, expires_at in self._sent.items() if expires_at <= now]
        for key in expired:
            self._sent.pop(key, None)


def _has_repeated_exact_pubg_evidence(result: Any) -> bool:
    """同一合法卡被原始 OCR 重复完整读取时，不把尾部噪声当成真实冲突。"""

    cards = tuple(str(card).upper() for card in (getattr(result, "cards", ()) or ()))
    if not cards or getattr(result, "psn_cards", ()):
        return False
    raw_text = str(getattr(result, "raw_text", "") or "").upper()
    if not raw_text:
        return False
    raw_cards = PUBG_CARD_RE.findall(raw_text)
    return set(raw_cards) == set(cards) and all(raw_cards.count(card) >= 2 for card in cards)


def _has_dominant_repeated_pubg_evidence(result: Any) -> bool:
    """Ignore one-off same-slot noise when one complete card repeats clearly."""

    cards = tuple(str(card).upper() for card in (getattr(result, "cards", ()) or ()))
    if len(cards) != 1 or getattr(result, "psn_cards", ()):
        return False
    confirmed = cards[0]
    raw_cards = PUBG_CARD_RE.findall(
        str(getattr(result, "raw_text", "") or "").upper()
    )
    confirmed_count = raw_cards.count(confirmed)
    if confirmed_count < 2:
        return False
    competing = [card for card in raw_cards if card != confirmed]
    if not competing:
        return True
    if not all(
        hamming_distance(compact_card(card), compact_card(confirmed)) == 1
        for card in competing
    ):
        return False
    highest_competing_count = max(competing.count(card) for card in set(competing))
    return confirmed_count > highest_competing_count
