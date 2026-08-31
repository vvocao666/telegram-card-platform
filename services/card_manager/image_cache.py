from __future__ import annotations

"""管理端原图缓存：固定 24 小时，不依赖现有 OCR 审计留存策略。"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import shutil


IMAGE_CACHE_HOURS = 24


@dataclass(frozen=True)
class CachedOriginalImage:
    path: str
    cached_at: str
    expires_at: str


def cache_original_image(
    source: Path,
    *,
    chat_id: int,
    message_id: int,
    image_index: int,
    file_unique_id: str,
    root: Path,
    now: datetime | None = None,
) -> CachedOriginalImage:
    """复制一份管理端核对图片；同一消息的图片只保留一份。"""
    created_at = now or datetime.now(UTC)
    expires_at = created_at + timedelta(hours=IMAGE_CACHE_HOURS)
    suffix = source.suffix.lower() if source.suffix else ".jpg"
    safe_unique_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in file_unique_id)[:80]
    name = f"{chat_id}_{message_id}_{image_index}_{safe_unique_id or 'image'}{suffix}"
    destination = root / created_at.strftime("%Y") / created_at.strftime("%m") / created_at.strftime("%d") / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
        timestamp = created_at.timestamp()
        os.utime(destination, (timestamp, timestamp))
    return CachedOriginalImage(
        path=str(destination),
        cached_at=created_at.isoformat(timespec="seconds"),
        expires_at=expires_at.isoformat(timespec="seconds"),
    )


def cleanup_expired_card_images(root: Path, *, now: datetime | None = None) -> int:
    """仅删除固定 24 小时前的管理端图片，绝不触碰卡密数据库。"""
    if not root.exists():
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=IMAGE_CACHE_HOURS)
    removed = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if modified_at <= cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    for directory in sorted((item for item in root.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed
