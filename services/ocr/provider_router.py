from __future__ import annotations

from datetime import datetime
from typing import Any, MutableMapping


DAILY_COUNTER_DEFAULTS = {
    "today_remote_calls": 0,
    "today_remote_success": 0,
    "today_remote_failed": 0,
    "today_fallback_count": 0,
    "today_remote_latency_total_ms": 0,
    "today_enhanced_used": 0,
    "today_cache_hits": 0,
    "today_remote_busy": 0,
}


def ensure_daily_counters(status: MutableMapping[str, Any], now: datetime) -> None:
    today = now.date().isoformat()
    if status.get("today_date") == today:
        return
    status.update({"today_date": today, **DAILY_COUNTER_DEFAULTS})


def circuit_is_open(offline_until: float, now: float) -> bool:
    return now < offline_until


def circuit_reason(offline_until: float, now: float) -> str:
    remaining = max(0, int(offline_until - now))
    if remaining <= 0:
        return "ok"
    return f"remote offline, retry in {remaining}s"


def fallback_reason(
    *,
    enabled: bool,
    url: str,
    offline_until: float,
    now: float,
    last_error: str,
) -> str:
    if not enabled:
        return "remote disabled"
    if not url:
        return "remote url empty"
    if circuit_is_open(offline_until, now):
        return circuit_reason(offline_until, now)
    return last_error or "remote unavailable"


def average_latency_ms(status: MutableMapping[str, Any]) -> int:
    success_count = int(status.get("today_remote_success", 0))
    if success_count <= 0:
        return 0
    return int(int(status.get("today_remote_latency_total_ms", 0)) / success_count)


def percent_rate(part: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{(part / total) * 100:.1f}%"


def current_provider(status: MutableMapping[str, Any], remote_label: str) -> str:
    if status.get("last_ok"):
        return remote_label
    if int(status.get("today_fallback_count", 0)) > 0:
        return "OCR.space"
    return "unknown"


def safe_remote_url(url: str) -> str:
    return url.split("?", 1)[0].replace("http://", "").replace("https://", "")
