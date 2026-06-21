from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path


DEFAULT_TODAY_OCR_CACHE_PATH = Path("outputs/today_ocr_cache.json")
LOCAL_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class TodayOcrCacheSummary:
    date: str
    images: int
    ocr_count: int
    first_cards: tuple[str, ...]
    path: str
    exists: bool


def append_today_ocr_cache(
    ocr_cards: list[str] | tuple[str, ...],
    raw_candidates: list[str] | tuple[str, ...] = tuple(),
    image_count: int = 1,
    path: Path | str = DEFAULT_TODAY_OCR_CACHE_PATH,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = now or datetime.now(LOCAL_TZ)
    current_date = current_time.strftime("%Y-%m-%d")
    cache_path = Path(path)
    data = _read_cache(cache_path)
    if data.get("date") != current_date:
        data = {
            "date": current_date,
            "images": 0,
            "ocr_cards": [],
            "raw_candidates": [],
            "time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    data["images"] = int(data.get("images", 0)) + image_count
    data["ocr_cards"] = _append_unique(_string_list(data.get("ocr_cards")), ocr_cards)
    data["raw_candidates"] = _append_unique(_string_list(data.get("raw_candidates")), raw_candidates)
    data["time"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def read_today_ocr_cache(
    path: Path | str = DEFAULT_TODAY_OCR_CACHE_PATH,
    now: datetime | None = None,
) -> dict[str, object] | None:
    cache_path = Path(path)
    if not cache_path.exists():
        return None
    data = _read_cache(cache_path)
    current_date = (now or datetime.now(LOCAL_TZ)).strftime("%Y-%m-%d")
    if data.get("date") != current_date:
        return None
    return data


def today_ocr_cache_summary(
    path: Path | str = DEFAULT_TODAY_OCR_CACHE_PATH,
    now: datetime | None = None,
) -> TodayOcrCacheSummary:
    cache_path = Path(path)
    data = read_today_ocr_cache(cache_path, now=now)
    if not data:
        return TodayOcrCacheSummary(
            date=(now or datetime.now(LOCAL_TZ)).strftime("%Y-%m-%d"),
            images=0,
            ocr_count=0,
            first_cards=tuple(),
            path=str(cache_path),
            exists=False,
        )
    cards = _string_list(data.get("ocr_cards"))
    return TodayOcrCacheSummary(
        date=str(data.get("date", "")),
        images=int(data.get("images", 0)),
        ocr_count=len(cards),
        first_cards=tuple(cards[:10]),
        path=str(cache_path),
        exists=True,
    )


def _read_cache(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _append_unique(existing: list[str], values: list[str] | tuple[str, ...]) -> list[str]:
    seen = set(existing)
    result = list(existing)
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]
