from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable


def record_remote_ocr_status(
    *,
    status: dict[str, Any],
    logger: logging.Logger,
    now_factory: Callable[[], datetime],
    ensure_today: Callable[[datetime | None], None],
    ok: bool,
    latency_ms: int,
    card_count: int = 0,
    text_count: int = 0,
    error: str = "",
    health_check: bool = False,
    enhanced_used: bool = False,
    cache_hit: bool = False,
) -> None:
    now = now_factory()
    ensure_today(now)
    if health_check:
        status["remote_health"] = ok
        status["last_checked_at"] = now.isoformat(timespec="seconds")
        if ok:
            logger.info("REMOTE OCR HEALTH OK")
        else:
            logger.info("REMOTE OCR HEALTH FAILED reason=%s", error)
        return

    if ok:
        status["today_remote_success"] += 1
        status["today_remote_latency_total_ms"] += latency_ms
        if enhanced_used:
            status["today_enhanced_used"] += 1
        if cache_hit:
            status["today_cache_hits"] += 1
        status["last_success_at"] = now.isoformat(timespec="seconds")
        logger.info(
            "REMOTE OCR SUCCESS latency_ms=%s cards=%s texts=%s enhanced_used=%s",
            latency_ms,
            card_count,
            text_count,
            str(enhanced_used).lower(),
        )
    else:
        status["today_remote_failed"] += 1
        status["last_failed_at"] = now.isoformat(timespec="seconds")
        logger.info("REMOTE OCR FAILED reason=%s", error)
    status.update(
        {
            "last_ok": ok,
            "last_error": error[:200],
            "last_latency_ms": latency_ms,
            "last_card_count": card_count,
            "last_checked_at": now.isoformat(timespec="seconds"),
        }
    )
