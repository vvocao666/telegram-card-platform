from __future__ import annotations

from typing import TypeVar


OcrResultT = TypeVar("OcrResultT")


def apply_card_corrections(chat_id: int, result: OcrResultT) -> OcrResultT:
    """保留兼容入口，但禁止用历史一次性卡密改写新的 OCR 结果。"""
    del chat_id
    return result


def learn_card_corrections_from_reply(update: object) -> None:
    """一次性完整卡密不建立可复用映射。"""
    del update
    return None


async def learn_ocr_sample_from_replied_photo(update: object, context: object) -> None:
    """旧图片文本到完整卡密的记忆入口已停用。"""
    del update, context
    return None
