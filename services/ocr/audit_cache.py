from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any


LOCAL_TZ = timezone(timedelta(hours=8))
DEFAULT_AUDIT_ROOT = Path("outputs/ocr_audit")
RETENTION_HOURS = 24 * 7


def stage_ocr_audit_image(
    image_path: Path,
    *,
    message_id: int,
    file_unique_id: str,
    media_group_id: str = "",
    source_chat_id: int = 0,
    source_chat_title: str = "",
    source_user_id: int = 0,
    source_username: str = "",
    root: Path | str = DEFAULT_AUDIT_ROOT,
    now: datetime | None = None,
) -> Path:
    """保存待审计原图，并返回该图片的记录目录。"""
    current_time = now or datetime.now(LOCAL_TZ)
    audit_root = Path(root)
    cleanup_expired_audits(audit_root, now=current_time)

    safe_unique_id = _safe_name(file_unique_id) or "unknown"
    record_name = f"{current_time:%H%M%S_%f}_{int(message_id)}_{safe_unique_id}"
    record_dir = audit_root / current_time.strftime("%Y-%m-%d") / record_name
    record_dir.mkdir(parents=True, exist_ok=False)

    suffix = image_path.suffix.lower() if image_path.suffix else ".jpg"
    saved_image = record_dir / f"original{suffix}"
    try:
        os.link(image_path, saved_image)
    except OSError:
        shutil.copy2(image_path, saved_image)
    _write_record(
        record_dir,
        {
            "created_at": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "message_id": int(message_id),
            "file_unique_id": file_unique_id,
            "media_group_id": media_group_id,
            "source": {
                "chat_id": int(source_chat_id),
                "chat_title": source_chat_title,
                "user_id": int(source_user_id),
                "username": source_username,
            },
            "image_file": saved_image.name,
            "status": "staged",
        },
    )
    return record_dir


def finalize_ocr_audit(
    record_dir: Path | None,
    *,
    batch_id: str,
    sequence_index: int,
    raw_result: Any,
    final_result: Any,
) -> None:
    """把原始 OCR 与最终输出绑定到同一张审计原图。"""
    if record_dir is None:
        return
    record = _read_record(record_dir)
    record.update(
        {
            "batch_id": batch_id,
            "sequence_index": int(sequence_index),
            "raw_text": str(getattr(raw_result, "raw_text", "")),
            "raw_cards": list(getattr(raw_result, "cards", ())),
            "raw_psn_cards": list(getattr(raw_result, "psn_ordered", ())),
            "final_cards": list(getattr(final_result, "cards", ())),
            "final_psn_cards": list(getattr(final_result, "psn_ordered", ())),
            "card_locations": [list(item) for item in getattr(final_result, "card_locations", ())],
            "psn_locations": [list(item) for item in getattr(final_result, "psn_locations", ())],
            "uncertain_count": int(getattr(final_result, "uncertain_count", 0)),
            "status": "complete",
        }
    )
    _write_record(record_dir, record)


def mark_ocr_audit_failed(record_dir: Path | None, reason: str) -> None:
    if record_dir is None:
        return
    record = _read_record(record_dir)
    record.update({"status": "failed", "error": str(reason)[:500]})
    _write_record(record_dir, record)


def cleanup_expired_audits(
    root: Path | str = DEFAULT_AUDIT_ROOT,
    *,
    now: datetime | None = None,
) -> int:
    audit_root = Path(root)
    if not audit_root.exists():
        return 0
    current_time = now or datetime.now(LOCAL_TZ)
    cutoff = current_time - timedelta(hours=RETENTION_HOURS)
    removed = 0
    for record_file in audit_root.glob("*/*/record.json"):
        record = _read_record(record_file.parent)
        created_at = _parse_time(str(record.get("created_at", "")))
        if created_at is None or created_at > cutoff:
            continue
        shutil.rmtree(record_file.parent)
        removed += 1
    for date_dir in audit_root.iterdir():
        if date_dir.is_dir() and not any(date_dir.iterdir()):
            date_dir.rmdir()
    return removed


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)[:80]


def _record_path(record_dir: Path) -> Path:
    return record_dir / "record.json"


def _read_record(record_dir: Path) -> dict[str, object]:
    path = _record_path(record_dir)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_record(record_dir: Path, record: dict[str, object]) -> None:
    path = _record_path(record_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=LOCAL_TZ)
