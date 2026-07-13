from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _remove_path(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
        return
    if path.is_dir():
        for child in path.iterdir():
            _remove_path(child)
        path.rmdir()
        return
    path.unlink(missing_ok=True)


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


def cleanup_server_file_records(
    *,
    enabled: bool,
    after_seconds: int,
    outputs_dir: Path,
    audit_root: Path,
    cleanup_audits: Callable[[Path], int],
    logger: Any,
    now: float | None = None,
    temp_root: Path | None = None,
    working_dir: Path | None = None,
) -> int:
    """清理服务器临时文件，持久数据目录只按明确白名单处理。"""
    if not enabled:
        return 0

    cutoff = (time.time() if now is None else now) - after_seconds
    removed = 0
    resolved_temp_root = temp_root or Path(tempfile.gettempdir())
    for path in resolved_temp_root.glob("s07_card_*"):
        try:
            if path.stat().st_mtime <= cutoff and _is_within_root(path, resolved_temp_root):
                _remove_path(path)
                removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Failed to clean temp path: %s", path)

    root = working_dir or Path.cwd()
    resolved_outputs = outputs_dir if outputs_dir.is_absolute() else root / outputs_dir
    resolved_audits = audit_root if audit_root.is_absolute() else root / audit_root
    removed += cleanup_expired_output_images(resolved_outputs, cutoff, logger=logger)
    removed += cleanup_audits(resolved_audits)
    if removed:
        logger.info("Cleaned %s old server file record(s).", removed)
    return removed
