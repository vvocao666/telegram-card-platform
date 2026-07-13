from __future__ import annotations

from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def cleanup_expired_output_images(output_root: Path, cutoff: float, *, logger: Any) -> int:
    """只清理明确的临时图片，持久数据库和学习文件永不参与。"""
    if not output_root.exists() or not output_root.is_dir():
        return 0

    removed = 0
    candidates = [
        path
        for path in output_root.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    preprocess_root = output_root / "preprocess"
    if preprocess_root.exists() and preprocess_root.is_dir():
        candidates.extend(path for path in preprocess_root.rglob("*") if path.is_file())

    output_resolved = output_root.resolve()
    for path in candidates:
        try:
            if not path.resolve().is_relative_to(output_resolved):
                continue
            if path.stat().st_mtime > cutoff:
                continue
            path.unlink(missing_ok=True)
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Failed to clean output image: %s", path)

    if preprocess_root.exists():
        for directory in sorted(
            (path for path in preprocess_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
    return removed
