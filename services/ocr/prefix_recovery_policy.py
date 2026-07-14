from __future__ import annotations

import re

from services.ocr.pubg_candidate_merge import is_same_slot_conflict


# 只识别 OCR 将 PUBG 固定首位 S 读成 5 的完整结构；正文字符不参与修复。
OBSERVED_FIVE_PREFIX_PUBG_RE = re.compile(
    r"(?<![A-Z0-9])50[0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}(?![A-Z0-9])"
)


def requires_cloud_confirmation(raw_text: str) -> bool:
    """首位 S 被读为 5 时，要求 OCR.space 对同一完整卡密独立复核。"""
    return bool(OBSERVED_FIVE_PREFIX_PUBG_RE.search(raw_text.upper()))


def choose_cloud_same_slot_card(
    remote_cards: tuple[str, ...],
    cloud_cards: tuple[str, ...],
    *,
    valid_card,
) -> str | None:
    """仅接受 OCR.space 对同一张完整卡密槽位给出的不同完整候选。"""
    if len(remote_cards) != 1 or len(cloud_cards) != 1:
        return None
    remote, cloud = remote_cards[0], cloud_cards[0]
    if remote == cloud or not valid_card(remote) or not valid_card(cloud):
        return None
    return cloud if is_same_slot_conflict(remote, cloud) else None
