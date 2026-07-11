from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Hashable
from typing import Any, TypeVar


T = TypeVar("T")


class OcrBatchJobPool:
    """图片到达时立即启动 OCR，批次结束时只负责按序收集结果。"""

    def __init__(self) -> None:
        self._tasks: dict[Hashable, asyncio.Task[Any]] = {}

    def start(self, key: Hashable, factory: Callable[[], Awaitable[T]]) -> asyncio.Task[T]:
        existing = self._tasks.get(key)
        if existing is not None:
            return existing
        task = asyncio.create_task(factory())
        self._tasks[key] = task
        return task

    async def take(self, key: Hashable, factory: Callable[[], Awaitable[T]]) -> T:
        task = self._tasks.pop(key, None)
        if task is None:
            task = asyncio.create_task(factory())
        return await task


class OcrBatchProgress:
    def __init__(
        self,
        message: Any,
        total: int,
        *,
        enabled: Callable[[], bool],
        minimum_images: Callable[[], int],
        update_seconds: Callable[[], float],
        clock: Callable[[], float],
        logger: Any,
    ) -> None:
        self.message = message
        self.total = total
        self.done = 0
        self.progress_message = None
        self.last_update_at = 0.0
        self.lock = asyncio.Lock()
        self._enabled = enabled
        self._minimum_images = minimum_images
        self._update_seconds = update_seconds
        self._clock = clock
        self._logger = logger

    async def start(self) -> None:
        if not self.should_show:
            return
        try:
            self.progress_message = await self.message.reply_text(self.text())
            self.last_update_at = self._clock()
        except Exception:
            self._logger.exception("Failed to send OCR progress message")

    @property
    def should_show(self) -> bool:
        return self._enabled() and self.total >= self._minimum_images()

    def text(self) -> str:
        if self.done <= 0:
            return f"正在识别 {self.total} 张图片，请稍候..."
        return f"正在识别 {self.total} 张图片，请稍候...\n处理进度：{self.done}/{self.total}"

    async def mark_done(self, force: bool = False) -> None:
        if not self.should_show:
            return
        async with self.lock:
            self.done = min(self.total, self.done + 1)
            if not self.progress_message:
                return
            now = self._clock()
            if not force and self.done < self.total and now - self.last_update_at < self._update_seconds():
                return
            try:
                await self.progress_message.edit_text(self.text())
                self.last_update_at = now
            except Exception as exc:
                self._logger.info("OCR progress update skipped: %s", exc)

    async def finish(self, has_result: bool) -> None:
        if not self.should_show or not self.progress_message:
            return
        try:
            await self.progress_message.delete()
        except Exception as exc:
            self._logger.info("OCR progress delete skipped: %s", exc)


class LiveOcrBatchProgress:
    """图片到达即显示进度，并在 OCR 后台并发执行时持续更新同一条消息。"""

    def __init__(
        self,
        message: Any,
        *,
        enabled: Callable[[], bool],
        update_seconds: Callable[[], float],
        clock: Callable[[], float],
        logger: Any,
    ) -> None:
        self.message = message
        self.total = 0
        self.done = 0
        self.has_card_result = False
        self.progress_message = None
        self.last_update_at = 0.0
        self.lock = asyncio.Lock()
        self._enabled = enabled
        self._update_seconds = update_seconds
        self._clock = clock
        self._logger = logger
        self._delayed_update: asyncio.Task[None] | None = None

    def register_image(self, message: Any) -> None:
        self.message = message
        self.total += 1

    def text(self) -> str:
        return (
            "正在识别图片，请稍候...\n"
            f"已收到：{self.total}张\n"
            f"处理进度：{self.done}/{self.total}"
        )

    async def publish(self, *, force: bool = False) -> None:
        if not self._enabled() or self.total < 2 or not self.has_card_result:
            return
        async with self.lock:
            if self.progress_message is None:
                try:
                    self.progress_message = await self.message.reply_text(self.text())
                    self.last_update_at = self._clock()
                except Exception:
                    self._logger.exception("Failed to send live OCR progress message")
                return
            now = self._clock()
            interval = min(max(self._update_seconds(), 0.1), 0.5)
            if not force and now - self.last_update_at < interval:
                self._schedule_delayed_update(interval - (now - self.last_update_at))
                return
            try:
                await self.progress_message.edit_text(self.text())
                self.last_update_at = now
            except Exception as exc:
                self._logger.info("Live OCR progress update skipped: %s", exc)

    def _schedule_delayed_update(self, delay: float) -> None:
        if self._delayed_update and not self._delayed_update.done():
            return

        async def update_later() -> None:
            await asyncio.sleep(max(delay, 0.05))
            await self.publish(force=True)

        self._delayed_update = asyncio.create_task(update_later())

    async def mark_done(self, *, has_card_result: bool = False) -> None:
        self.has_card_result = self.has_card_result or has_card_result
        self.done = min(self.total, self.done + 1)
        await self.publish(force=self.done >= self.total)

    async def finish(self, has_result: bool) -> None:
        if self._delayed_update and not self._delayed_update.done():
            self._delayed_update.cancel()
        if not self._enabled() or self.progress_message is None:
            return
        try:
            await self.progress_message.delete()
        except Exception as exc:
            self._logger.info("Live OCR progress delete skipped: %s", exc)


def order_batch_updates(updates: list[Any], key: Callable[[Any], tuple[int, int]]) -> list[Any]:
    return sorted(updates, key=key)


def order_batch_results(results: list[tuple[int, Any, Any, bool]]) -> list[tuple[int, Any, Any, bool]]:
    return sorted(results, key=lambda item: item[0])


def batch_debounce_seconds(
    *,
    owner_photo: bool,
    owner_bulk_photo: bool,
    batch_size: int,
    single_wait_seconds: float,
    multi_wait_seconds: float,
    owner_bulk_wait_seconds: float,
) -> float:
    """连续发送的 owner 图片也等待完整批次，避免按网络到达间隔拆批。"""
    if owner_bulk_photo:
        return owner_bulk_wait_seconds
    if owner_photo:
        return 0.05
    if batch_size > 1:
        return multi_wait_seconds
    return single_wait_seconds
