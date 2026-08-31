from __future__ import annotations

"""把已完成且已排序的 OCR 结果投递到卡密管理端数据层。"""

from datetime import UTC, datetime
import re
from typing import Any, Callable, Mapping

from storage.repositories.card_manager_storage import CardManagerStore, CardRecordInput


_PUBG_CANDIDATE_RE = re.compile(
    r"(?<![A-Z0-9])S0?7[A-Z0-9]{3}(?:[-\s_]+[A-Z0-9]{2,8}){1,4}",
    re.IGNORECASE,
)
# 完整分段没有读全时，只要还保留 PUBG S07 的明确开头，就进入人工核对。
# 这是管理端的旁路采集，不参与机器人 OCR 识别、回复或判定。
_PUBG_PARTIAL_CANDIDATE_RE = re.compile(r"(?<![A-Z0-9])S0?7[A-Z0-9]{3}(?![A-Z0-9])", re.IGNORECASE)
_GENERIC_CARD_CANDIDATE_RE = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z0-9]{4,6}[-\s_]){2,3}[A-Z0-9]{4,6}(?![A-Z0-9])",
    re.IGNORECASE,
)


def has_manual_review_card_candidate(raw_text: str) -> bool:
    """只把看起来像卡密的 OCR 失败图片留给人工审核。

    管理端是机器人 OCR 的旁路：付款二维码、转账截图等没有任何卡密特征的
    图片不应生成空白表格行；但包含不完整或识别错误卡密的图片必须保留，供
    用户对照原图手工修改。本函数不参与机器人回复或 OCR 判定。
    """
    return bool(
        _PUBG_CANDIDATE_RE.search(raw_text)
        or _PUBG_PARTIAL_CANDIDATE_RE.search(raw_text)
        or _GENERIC_CARD_CANDIDATE_RE.search(raw_text)
    )


def persist_ocr_batch(
    store: CardManagerStore,
    *,
    updates: list[Any],
    final_results: list[Any],
    raw_results: list[Any],
    images_by_update: Mapping[int, Any],
    result_card_lines: Callable[[list[Any]], tuple[list[str], list[str]]],
) -> list[int]:
    """保存最终输出，且绝不向 OCR 流程抛出业务异常。

    `updates` 已在调用处按 Telegram 原始消息排序；`image_index` 因而不会受 OCR
    并发完成先后影响。图片缓存元数据来自下载完成后的旁路副本。
    """
    inputs: list[CardRecordInput] = []
    for image_index, (update, final_result, raw_result) in enumerate(
        zip(updates, final_results, raw_results), start=1
    ):
        message = getattr(update, "message", None)
        if message is None:
            continue
        chat = getattr(update, "effective_chat", None)
        user = getattr(update, "effective_user", None)
        photo_sizes = getattr(message, "photo", None) or ()
        photo = photo_sizes[-1] if photo_sizes else None
        image = images_by_update.get(id(update))
        final_pubg, final_psn = result_card_lines([final_result])
        raw_pubg, raw_psn = result_card_lines([raw_result])
        entries = (
            ("PUBG", final_pubg, raw_pubg),
            ("PSN", final_psn, raw_psn),
        )
        card_index = 0
        for card_type, final_cards, raw_cards in entries:
            for position, final_card in enumerate(final_cards):
                card_index += 1
                original_card = raw_cards[position] if position < len(raw_cards) else final_card
                inputs.append(
                    CardRecordInput(
                        telegram_chat_id=int(getattr(chat, "id", 0) or 0),
                        telegram_chat_title=str(getattr(chat, "title", "") or getattr(chat, "full_name", "") or ""),
                        telegram_user_id=int(getattr(user, "id", 0) or 0),
                        telegram_user_name=str(getattr(user, "full_name", "") or ""),
                        telegram_user_username=str(getattr(user, "username", "") or ""),
                        telegram_message_id=int(getattr(message, "message_id", 0) or 0),
                        telegram_message_date=_message_time(getattr(message, "date", None)),
                        media_group_id=str(getattr(message, "media_group_id", "") or ""),
                        image_index=image_index,
                        card_index=card_index,
                        card_type=card_type,
                        ocr_original_card=original_card,
                        final_card=final_card,
                        denomination="未分类",
                        original_image_path=str(getattr(image, "path", "") or ""),
                        telegram_file_id=str(getattr(photo, "file_id", "") or ""),
                        telegram_file_unique_id=str(getattr(photo, "file_unique_id", "") or ""),
                        image_cached_at=str(getattr(image, "cached_at", "") or ""),
                        image_expires_at=str(getattr(image, "expires_at", "") or ""),
                    )
                )
        # OCR 没有最终输出时，仅当原始文本仍有疑似卡密特征才留给人工审核。
        # 付款码、二维码等无关图片不会在管理端生成空白行；这不会改变机器人
        # 回复、重复判断或现有 OCR 的任何分支。
        # 不同 OCR 结果对象偶尔只有其中一层保留残缺文字；两层合并后再判断，
        # 只影响管理端是否建立人工核对行，不影响机器人最终识别结果。
        raw_text = "\n".join(
            str(getattr(result, "raw_text", "") or "")
            for result in (raw_result, final_result)
        )
        if card_index == 0 and has_manual_review_card_candidate(raw_text):
            inputs.append(
                CardRecordInput(
                    telegram_chat_id=int(getattr(chat, "id", 0) or 0),
                    telegram_chat_title=str(getattr(chat, "title", "") or getattr(chat, "full_name", "") or ""),
                    telegram_user_id=int(getattr(user, "id", 0) or 0),
                    telegram_user_name=str(getattr(user, "full_name", "") or ""),
                    telegram_user_username=str(getattr(user, "username", "") or ""),
                    telegram_message_id=int(getattr(message, "message_id", 0) or 0),
                    telegram_message_date=_message_time(getattr(message, "date", None)),
                    media_group_id=str(getattr(message, "media_group_id", "") or ""),
                    image_index=image_index,
                    card_index=1,
                    card_type="UNKNOWN",
                    ocr_original_card="",
                    final_card="",
                    denomination="未分类",
                    original_image_path=str(getattr(image, "path", "") or ""),
                    telegram_file_id=str(getattr(photo, "file_id", "") or ""),
                    telegram_file_unique_id=str(getattr(photo, "file_unique_id", "") or ""),
                    image_cached_at=str(getattr(image, "cached_at", "") or ""),
                    image_expires_at=str(getattr(image, "expires_at", "") or ""),
                    ocr_failed=True,
                )
            )
    return store.record_ocr_cards(inputs)


def _message_time(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="seconds")
    return datetime.now(UTC).isoformat(timespec="seconds")
