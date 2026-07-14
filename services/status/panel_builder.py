from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from services.status.status_service import StatusPanelSnapshot, render_status_panel


@dataclass(frozen=True)
class StatusPanelHooks:
    ensure_today: Callable[[], None]
    worker_health: Callable[[], tuple[bool, dict[str, Any], str]]
    cache_counts: Callable[[], dict[str, int]]
    service_state: Callable[[], str]
    git_output: Callable[[list[str]], str]
    process_memory_mb: Callable[[], str]
    process_uptime_text: Callable[[], str]
    average_remote_latency_ms: Callable[[], int]
    format_time_value: Callable[[object], str]
    percent_rate: Callable[[int, int], str]
    status: dict[str, Any]
    ledger_path: Path
    remote_label: str
    remote_enabled: bool
    ocrspace_available: bool


def build_status_panel(hooks: StatusPanelHooks) -> str:
    hooks.ensure_today()
    worker_ok, worker_payload, worker_error = hooks.worker_health()
    hooks.status["remote_health"] = worker_ok
    remote_calls = int(hooks.status["today_remote_calls"])
    cache_counts = hooks.cache_counts()
    worker_status = str(worker_payload.get("status", "ok" if worker_ok else "offline"))
    metrics = worker_payload.get("stats")
    metrics = metrics if isinstance(metrics, dict) else {}
    queue = worker_payload.get("queue")
    queue = queue if isinstance(queue, dict) else {}
    cpu = worker_payload.get("cpu_ocr")
    cpu = cpu if isinstance(cpu, dict) else {}
    current_provider = hooks.remote_label if worker_ok else "OCR.space"
    return render_status_panel(
        StatusPanelSnapshot(
            service_state=hooks.service_state(),
            branch=hooks.git_output(["branch", "--show-current"]),
            commit=hooks.git_output(["rev-parse", "--short", "HEAD"]),
            memory=hooks.process_memory_mb(),
            uptime=hooks.process_uptime_text(),
            ledger_exists=hooks.ledger_path.exists(),
            remote_label=hooks.remote_label,
            remote_enabled=hooks.remote_enabled,
            worker_ok=worker_ok,
            worker_status=worker_status if worker_ok else worker_error,
            worker_gpu=str(worker_payload.get("gpu", "unknown")),
            worker_engine=str(worker_payload.get("engine", "unknown")),
            avg_remote_latency_ms=hooks.average_remote_latency_ms(),
            last_success=hooks.format_time_value(hooks.status.get("last_success_at")),
            last_failed=hooks.format_time_value(hooks.status.get("last_failed_at")),
            last_error=str(hooks.status.get("last_error") or "无"),
            current_provider=current_provider,
            ocrspace_available=hooks.ocrspace_available,
            remote_calls=remote_calls,
            remote_success=int(hooks.status["today_remote_success"]),
            remote_failed=int(hooks.status["today_remote_failed"]),
            fallback_count=int(hooks.status["today_fallback_count"]),
            cache_hit_rate=hooks.percent_rate(int(hooks.status["today_cache_hits"]), remote_calls),
            enhanced_rate=hooks.percent_rate(int(hooks.status["today_enhanced_used"]), remote_calls),
            image_count=cache_counts["images"],
            card_count=cache_counts["cards"],
            pubg_count=cache_counts["pubg"],
            psn_count=cache_counts["psn"],
            duplicate_count=cache_counts["duplicates"],
            worker_cpu_status=_cpu_status(worker_ok, cpu, metrics),
            worker_gpu_tasks=_metric(metrics, "gpu_runs", "requests"),
            worker_cpu_tasks=_metric(metrics, "cpu_ocr_runs"),
            worker_gpu_avg_ms=_metric(metrics, "gpu_latency_avg_ms"),
            worker_cpu_avg_ms=_metric(metrics, "cpu_ocr_avg_ms"),
            worker_queue_depth=_metric(queue, "active") + _metric(queue, "queued"),
            worker_cache_hits=_metric(metrics, "cache_hits"),
            worker_conflicts=_metric(metrics, "cpu_conflicts") + _metric(metrics, "roi_reviews"),
        )
    )


def _metric(values: dict[str, Any], *names: str) -> int:
    for name in names:
        try:
            return max(0, int(values.get(name, 0)))
        except (TypeError, ValueError):
            continue
    return 0


def _cpu_status(worker_ok: bool, cpu: dict[str, Any], metrics: dict[str, Any]) -> str:
    if not worker_ok:
        return "离线"
    if not cpu.get("enabled"):
        return "未启用"
    if not cpu.get("available"):
        return "异常"
    runs = _metric(metrics, "cpu_ocr_runs")
    suffix = "影子验证" if cpu.get("shadow_only") else "受控复核"
    return f"在线，{'已运行' if runs else '未运行'}（{suffix}）"
