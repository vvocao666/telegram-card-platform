from datetime import datetime, timezone, timedelta

from services.ocr.today_cache import append_today_ocr_cache, read_today_ocr_cache, today_ocr_cache_summary


TZ = timezone(timedelta(hours=8))


def test_today_ocr_cache_create_append_and_dedupe(tmp_path):
    path = tmp_path / "outputs" / "today_ocr_cache.json"
    now = datetime(2026, 6, 21, 21, 15, tzinfo=TZ)

    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], ["raw1"], path=path, now=now)
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC", "S07304-DDDD-EEEE-FFFFF"], ["raw1", "raw2"], path=path, now=now)
    data = read_today_ocr_cache(path, now=now)

    assert data["date"] == "2026-06-21"
    assert data["images"] == 2
    assert data["ocr_cards"] == ["S07304-AAAA-BBBB-CCCCC", "S07304-DDDD-EEEE-FFFFF"]
    assert data["raw_candidates"] == ["raw1", "raw2"]


def test_today_ocr_cache_counts_images_separately_from_cards(tmp_path):
    path = tmp_path / "outputs" / "today_ocr_cache.json"
    now = datetime(2026, 6, 21, 21, 15, tzinfo=TZ)

    append_today_ocr_cache(
        ["S07304-AAAA-BBBB-CCCCC", "S07304-DDDD-EEEE-FFFFF", "S07304-GGGG-HHHH-IIIII"],
        path=path,
        now=now,
    )
    data = read_today_ocr_cache(path, now=now)
    summary = today_ocr_cache_summary(path, now=now)

    assert data["images"] == 1
    assert summary.images == 1
    assert summary.ocr_count == 3


def test_today_ocr_cache_duplicate_card_still_counts_new_image(tmp_path):
    path = tmp_path / "outputs" / "today_ocr_cache.json"
    now = datetime(2026, 6, 21, 21, 15, tzinfo=TZ)

    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=path, now=now)
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=path, now=now)
    data = read_today_ocr_cache(path, now=now)
    summary = today_ocr_cache_summary(path, now=now)

    assert data["images"] == 2
    assert data["ocr_cards"] == ["S07304-AAAA-BBBB-CCCCC"]
    assert summary.images == 2
    assert summary.ocr_count == 1


def test_today_ocr_cache_resets_across_days(tmp_path):
    path = tmp_path / "outputs" / "today_ocr_cache.json"
    first = datetime(2026, 6, 21, 23, 59, tzinfo=TZ)
    second = datetime(2026, 6, 22, 0, 1, tzinfo=TZ)

    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=path, now=first)
    append_today_ocr_cache(["S07304-DDDD-EEEE-FFFFF"], path=path, now=second)
    data = read_today_ocr_cache(path, now=second)

    assert data["date"] == "2026-06-22"
    assert data["ocr_cards"] == ["S07304-AAAA-BBBB-CCCCC", "S07304-DDDD-EEEE-FFFFF"]


def test_today_ocr_cache_keeps_only_recent_twenty_four_hours(tmp_path):
    path = tmp_path / "outputs" / "today_ocr_cache.json"
    old = datetime(2026, 6, 21, 21, 0, tzinfo=TZ)
    now = datetime(2026, 6, 22, 22, 0, tzinfo=TZ)

    append_today_ocr_cache(["S07304-OLD1-BBBB-CCCCC"], path=path, now=old)
    append_today_ocr_cache(["S07304-NEWW-BBBB-CCCCC"], path=path, now=now)
    data = read_today_ocr_cache(path, now=now)

    assert data["ocr_cards"] == ["S07304-NEWW-BBBB-CCCCC"]


def test_today_ocr_cache_duplicate_cards_do_not_participate_twice(tmp_path):
    path = tmp_path / "outputs" / "today_ocr_cache.json"
    now = datetime(2026, 6, 22, 22, 0, tzinfo=TZ)

    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=path, now=now)
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=path, now=now)
    data = read_today_ocr_cache(path, now=now)

    assert data["ocr_cards"] == ["S07304-AAAA-BBBB-CCCCC"]
    assert len(data["ocr_entries"]) == 1


def test_today_ocr_cache_summary_missing(tmp_path):
    path = tmp_path / "outputs" / "today_ocr_cache.json"

    summary = today_ocr_cache_summary(path, now=datetime(2026, 6, 21, tzinfo=TZ))

    assert not summary.exists
    assert summary.images == 0
    assert summary.ocr_count == 0
