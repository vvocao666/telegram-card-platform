from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path


DEFAULT_TODAY_OCR_CACHE_PATH = Path("outputs/today_ocr_cache.json")
LOCAL_TZ = timezone(timedelta(hours=8))
RETENTION_HOURS = 24


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
    if not data:
        data = {
            "date": current_date,
            "images": 0,
            "ocr_cards": [],
            "raw_candidates": [],
            "ocr_entries": [],
            "time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    data["ocr_entries"] = _retained_entries(data, current_time)
    data["images"] = int(data.get("images", 0)) + image_count
    data["ocr_entries"] = _append_entry_cards(_entry_list(data.get("ocr_entries")), ocr_cards, current_time)
    data["ocr_cards"] = _cards_from_entries(_entry_list(data.get("ocr_entries")))
    data["raw_candidates"] = _append_unique(_string_list(data.get("raw_candidates")), raw_candidates)
    data["date"] = current_date
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
    if not data:
        return None
    current_time = now or datetime.now(LOCAL_TZ)
    retained = _retained_entries(data, current_time)
    if retained:
        data["ocr_entries"] = retained
        data["ocr_cards"] = _cards_from_entries(retained)
        return data
    cache_time = _parse_time(str(data.get("time") or ""))
    if cache_time and current_time - cache_time <= timedelta(hours=RETENTION_HOURS):
        return data
    if data.get("date") == current_time.strftime("%Y-%m-%d"):
        return data
    return None


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


def _retained_entries(data: dict[str, object], now: datetime) -> list[dict[str, str]]:
    entries = _entry_list(data.get("ocr_entries"))
    if not entries:
        cache_time = _parse_time(str(data.get("time") or ""))
        if cache_time and now - cache_time <= timedelta(hours=RETENTION_HOURS):
            time_text = _format_time(cache_time)
            return [{"card": card, "time": time_text} for card in _string_list(data.get("ocr_cards"))]
        return []
    retained: list[dict[str, str]] = []
    for entry in entries:
        entry_time = _parse_time(entry.get("time", ""))
        if entry_time and now - entry_time <= timedelta(hours=RETENTION_HOURS):
            retained.append(entry)
    return retained


def _append_entry_cards(
    existing: list[dict[str, str]],
    values: list[str] | tuple[str, ...],
    now: datetime,
) -> list[dict[str, str]]:
    seen = {entry["card"] for entry in existing if entry.get("card")}
    result = list(existing)
    time_text = _format_time(now)
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append({"card": str(value), "time": time_text})
    return result


def _cards_from_entries(entries: list[dict[str, str]]) -> list[str]:
    seen: set[str] = set()
    cards: list[str] = []
    for entry in entries:
        card = entry.get("card")
        if not card or card in seen:
            continue
        seen.add(card)
        cards.append(card)
    return cards


def _entry_list(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    entries: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        card = item.get("card")
        time_text = item.get("time")
        if isinstance(card, str) and card:
            entries.append({"card": card, "time": str(time_text or "")})
    return entries


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=LOCAL_TZ)
        except ValueError:
            continue
    return None


def _format_time(value: datetime) -> str:
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


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
