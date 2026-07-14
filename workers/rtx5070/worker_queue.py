from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Any, Callable


class WorkerQueueFull(RuntimeError):
    pass


class WorkerTaskQueue:
    """限制进入 Worker 的任务数；GPU 仍由独立信号量串行执行。"""

    def __init__(self, workers: int, capacity: int) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="ocr-worker")
        self._slots = threading.BoundedSemaphore(max(1, capacity))
        self._lock = threading.Lock()
        self._active = 0
        self._queued = 0
        self._capacity = max(1, capacity)

    async def run(self, callback: Callable[..., Any], *args: Any) -> Any:
        if not self._slots.acquire(blocking=False):
            raise WorkerQueueFull("worker queue full")
        with self._lock:
            self._queued += 1
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, self._invoke, callback, args)
        finally:
            self._slots.release()

    def _invoke(self, callback: Callable[..., Any], args: tuple[Any, ...]) -> Any:
        with self._lock:
            self._queued = max(0, self._queued - 1)
            self._active += 1
        try:
            return callback(*args)
        finally:
            with self._lock:
                self._active = max(0, self._active - 1)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"active": self._active, "queued": self._queued, "capacity": self._capacity}
