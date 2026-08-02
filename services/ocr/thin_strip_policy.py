from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps


PUBG_CARD_RE = re.compile(
    r"(?<![A-Z0-9])S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}(?![A-Z0-9])"
)


def is_thin_strip_image(
    image_path: Path,
    *,
    maximum_height: int = 200,
    minimum_aspect_ratio: float = 2.5,
) -> bool:
    """仅识别明显的单行细长截图，避免改变普通图片 OCR 路径。"""
    try:
        with Image.open(image_path) as opened:
            image = ImageOps.exif_transpose(opened)
            width, height = image.size
    except (OSError, ValueError):
        return False
    return height > 0 and height <= maximum_height and width / height >= minimum_aspect_ratio


def choose_thin_strip_result(
    remote: Any,
    cloud: Any,
    *,
    valid_card: Callable[[str], bool],
) -> tuple[Any, bool]:
    """细长 PUBG 单卡图以完整合法的 OCR.space 结果校验 RTX 结果。"""
    cloud_cards = tuple(getattr(cloud, "cards", ()) or ())
    cloud_psn = tuple(getattr(cloud, "psn_cards", ()) or ())
    cloud_psn_uncertain = tuple(getattr(cloud, "psn_uncertain", ()) or ())
    if (
        len(cloud_cards) != 1
        or cloud_psn
        or cloud_psn_uncertain
        or int(getattr(cloud, "uncertain_count", 0) or 0) != 0
        or not valid_card(cloud_cards[0])
    ):
        return remote, False

    remote_cards = tuple(getattr(remote, "cards", ()) or ())
    remote_is_valid = (
        len(remote_cards) == 1
        and not tuple(getattr(remote, "psn_cards", ()) or ())
        and not tuple(getattr(remote, "psn_uncertain", ()) or ())
        and valid_card(remote_cards[0])
    )
    if not remote_is_valid:
        return cloud, False
    if remote_cards == cloud_cards:
        return cloud, False
    repeated_cloud_card = repeated_cloud_same_slot_card(
        remote,
        cloud,
        valid_card=valid_card,
    )
    if repeated_cloud_card is not None:
        return cloud, False
    return remote, True


def repeated_cloud_same_slot_card(
    remote: Any,
    cloud: Any,
    *,
    valid_card: Callable[[str], bool],
) -> str | None:
    """Accept repeated cloud evidence for one duplicated thin-strip slot.

    Card/password screenshots can display one card on two adjacent rows. This
    policy never edits a glyph: it accepts only one complete cloud card seen at
    least twice, while every complete GPU reading retains the same prefix and
    first two body groups.
    """

    cloud_cards = tuple(str(card).upper() for card in (getattr(cloud, "cards", ()) or ()))
    if len(cloud_cards) != 1 or not valid_card(cloud_cards[0]):
        return None
    confirmed = cloud_cards[0]
    cloud_raw_cards = PUBG_CARD_RE.findall(str(getattr(cloud, "raw_text", "") or "").upper())
    if cloud_raw_cards.count(confirmed) < 2 or any(card != confirmed for card in cloud_raw_cards):
        return None

    remote_raw_cards = PUBG_CARD_RE.findall(
        str(getattr(remote, "raw_text", "") or "").upper()
    )
    remote_cards = tuple(
        str(card).upper() for card in (getattr(remote, "cards", ()) or ())
    )
    evidence = list(dict.fromkeys((*remote_cards, *remote_raw_cards)))
    if not evidence or any(not valid_card(card) for card in evidence):
        return None

    confirmed_parts = confirmed.split("-")
    if len(confirmed_parts) != 4:
        return None
    if any(card.split("-")[:3] != confirmed_parts[:3] for card in evidence):
        return None
    return confirmed
