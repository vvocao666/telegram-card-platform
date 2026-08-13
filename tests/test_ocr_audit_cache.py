from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from services.ocr.audit_cache import cleanup_expired_audits, finalize_ocr_audit, stage_ocr_audit_image


TZ = timezone(timedelta(hours=8))


@dataclass
class Result:
    cards: tuple[str, ...]
    raw_text: str = ""
    psn_ordered: tuple[str, ...] = tuple()
    card_locations: tuple[tuple[str, int, int], ...] = tuple()
    psn_locations: tuple[tuple[str, int, int], ...] = tuple()
    uncertain_count: int = 0


def test_audit_cache_saves_original_and_final_result(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image-data")
    now = datetime(2026, 7, 11, 12, 15, tzinfo=TZ)

    record_dir = stage_ocr_audit_image(
        source,
        message_id=123,
        file_unique_id="file-id",
        media_group_id="album-1",
        root=tmp_path / "audit",
        now=now,
    )
    raw = Result(cards=("S07336-AAAA-BBBB-CCCCC",), raw_text="raw line")
    final = Result(
        cards=("S07336-AAAA-BBBB-CCCCC",),
        raw_text="raw line",
        card_locations=(("S07336-AAAA-BBBB-CCCCC", 10, 20),),
    )
    finalize_ocr_audit(record_dir, batch_id="batch-1", sequence_index=2, raw_result=raw, final_result=final)

    assert (record_dir / "original.jpg").read_bytes() == b"image-data"
    record_text = (record_dir / "record.json").read_text(encoding="utf-8")
    assert '"sequence_index": 2' in record_text
    assert '"batch_id": "batch-1"' in record_text
    assert '"status": "complete"' in record_text
    assert "S07336-AAAA-BBBB-CCCCC" in record_text


def test_audit_cache_removes_only_records_older_than_seven_days(tmp_path):
    root = tmp_path / "audit"
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image-data")
    now = datetime(2026, 7, 11, 12, 15, tzinfo=TZ)
    current_record = stage_ocr_audit_image(
        source,
        message_id=2,
        file_unique_id="current",
        root=root,
        now=now,
    )
    old_record = stage_ocr_audit_image(
        source,
        message_id=1,
        file_unique_id="old",
        root=root,
        now=now - timedelta(days=8),
    )

    assert cleanup_expired_audits(root, now=now) == 1
    assert not old_record.exists()
    assert current_record.exists()


def test_audit_cache_records_original_telegram_message_time(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image-data")
    staged_at = datetime(2026, 8, 14, 0, 1, tzinfo=TZ)
    message_at_utc = datetime(2026, 8, 13, 15, 59, tzinfo=timezone.utc)

    record_dir = stage_ocr_audit_image(
        source,
        message_id=456,
        file_unique_id="original-time",
        message_created_at=message_at_utc,
        root=tmp_path / "audit",
        now=staged_at,
    )
    record = json.loads((record_dir / "record.json").read_text(encoding="utf-8"))

    assert record_dir.parent.name == "2026-08-13"
    assert record["message_created_at"] == "2026-08-13 23:59:00"
    assert record["created_at"] == "2026-08-14 00:01:00"
