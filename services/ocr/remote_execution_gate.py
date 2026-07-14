from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import threading
import time
from typing import Iterator


class RemoteWorkerBusy(RuntimeError):
    """云端在途请求已达到受控上限，Worker 并非离线。"""


@dataclass(frozen=True)
class RemoteGateSnapshot:
    active: int
    waiting: int
    rejected: int
    max_active: int
    last_wait_ms: int


class RemoteExecutionGate:
    """限制云端到单 GPU Worker 的在途 HTTP 请求，防止请求线程堆积。"""

    def __init__(self, max_active: int) -> None:
        self._max_active = max(1, int(max_active))
        self._semaphore = threading.BoundedSemaphore(self._max_active)
        self._lock = threading.Lock()
        self._active = 0
        self._waiting = 0
        self._rejected = 0
        self._last_wait_ms = 0

    @contextmanager
    def slot(self, wait_seconds: float) -> Iterator[int]:
        started_at = time.monotonic()
        with self._lock:
            self._waiting += 1
        acquired = self._semaphore.acquire(timeout=max(0.0, float(wait_seconds)))
        waited_ms = int((time.monotonic() - started_at) * 1000)
        with self._lock:
            self._waiting -= 1
            self._last_wait_ms = waited_ms
            if acquired:
                self._active += 1
            else:
                self._rejected += 1
        if not acquired:
            raise RemoteWorkerBusy("remote execution gate full")
        try:
            yield waited_ms
        finally:
            with self._lock:
                self._active = max(0, self._active - 1)
            self._semaphore.release()

    def snapshot(self) -> RemoteGateSnapshot:
        with self._lock:
            return RemoteGateSnapshot(
                active=self._active,
                waiting=self._waiting,
                rejected=self._rejected,
                max_active=self._max_active,
                last_wait_ms=self._last_wait_ms,
            )
