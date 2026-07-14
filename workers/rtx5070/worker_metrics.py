from __future__ import annotations

from contextlib import contextmanager
import threading
import time
from typing import Iterator


class WorkerMetrics:
    """有界汇总指标，避免保存每张图片或用户数据。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values = {
            "requests": 0,
            "cache_hits": 0,
            "gpu_active": 0,
            "gpu_waiting": 0,
            "gpu_wait_total_ms": 0,
            "gpu_runs": 0,
            "gpu_latency_total_ms": 0,
            "cpu_preprocess_runs": 0,
            "cpu_preprocess_total_ms": 0,
            "cpu_ocr_runs": 0,
            "cpu_ocr_total_ms": 0,
            "cpu_ocr_failures": 0,
            "cpu_conflicts": 0,
            "roi_reviews": 0,
            "queue_rejected": 0,
        }

    def increment(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._values[key] = int(self._values.get(key, 0)) + amount

    def observe(self, prefix: str, elapsed_ms: int) -> None:
        with self._lock:
            self._values[f"{prefix}_runs"] = int(self._values.get(f"{prefix}_runs", 0)) + 1
            self._values[f"{prefix}_total_ms"] = int(self._values.get(f"{prefix}_total_ms", 0)) + max(0, elapsed_ms)

    def gpu_wait_started(self) -> float:
        waiting_at = time.monotonic()
        with self._lock:
            self._values["gpu_waiting"] += 1
        return waiting_at

    def gpu_wait_finished(self, waiting_at: float) -> None:
        wait_ms = int((time.monotonic() - waiting_at) * 1000)
        with self._lock:
            self._values["gpu_waiting"] = max(0, self._values["gpu_waiting"] - 1)
            self._values["gpu_wait_total_ms"] += wait_ms

    def gpu_started(self) -> float:
        with self._lock:
            self._values["gpu_active"] += 1
        return time.monotonic()

    def gpu_finished(self, started_at: float) -> None:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        with self._lock:
            self._values["gpu_active"] = max(0, self._values["gpu_active"] - 1)
            self._values["gpu_runs"] += 1
            self._values["gpu_latency_total_ms"] += elapsed_ms

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            values = dict(self._values)
        values["gpu_wait_avg_ms"] = _average(values["gpu_wait_total_ms"], values["gpu_runs"])
        values["gpu_latency_avg_ms"] = _average(values["gpu_latency_total_ms"], values["gpu_runs"])
        values["cpu_preprocess_avg_ms"] = _average(values["cpu_preprocess_total_ms"], values["cpu_preprocess_runs"])
        values["cpu_ocr_avg_ms"] = _average(values["cpu_ocr_total_ms"], values["cpu_ocr_runs"])
        return values


def _average(total: int, count: int) -> int:
    return int(total / count) if count else 0
