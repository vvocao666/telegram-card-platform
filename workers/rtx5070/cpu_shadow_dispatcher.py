from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import os
import tempfile
import threading
from typing import Any


LOGGER = logging.getLogger("rtx5070_worker.cpu_shadow")


class CpuShadowDispatcher:
    """Run low-risk CPU evidence outside the request critical path."""

    def __init__(self, engine: Any, config: Any, metrics: Any) -> None:
        self._engine = engine
        self._metrics = metrics
        workers = max(1, int(config.cpu_ocr_workers))
        self._enabled = bool(
            config.cpu_ocr_effective and config.cpu_async_shadow_enabled
        )
        self._slots = threading.BoundedSemaphore(workers * 2)
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="cpu-ocr-shadow"
        )

    def submit(
        self,
        image_bytes: bytes,
        suffix: str,
        texts: list[dict[str, Any]],
    ) -> bool:
        if not self._enabled or not self._slots.acquire(blocking=False):
            if self._enabled:
                self._metrics.increment("cpu_shadow_dropped")
            return False
        self._metrics.increment("cpu_shadow_deferred")
        self._executor.submit(self._run, bytes(image_bytes), suffix, list(texts))
        return True

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, image_bytes: bytes, suffix: str, texts: list[dict[str, Any]]) -> None:
        path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(image_bytes)
                path = handle.name
            payload = self._engine.inspect_gpu_lines(path, texts)
            if payload.get("conflicts"):
                LOGGER.info(
                    "CPU SHADOW CONFLICT lines=%s conflicts=%s",
                    len(payload.get("lines", [])),
                    len(payload.get("conflicts", [])),
                )
        except Exception as exc:
            self._metrics.increment("cpu_ocr_failures")
            LOGGER.warning("CPU SHADOW FAILED reason=%s", type(exc).__name__)
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            self._slots.release()
