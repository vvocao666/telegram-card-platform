from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps


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
    return remote, True
