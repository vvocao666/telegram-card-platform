from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


CleanupCallback = Callable[[], int]
AsyncLoopFactory = Callable[[], Awaitable[None]]
CloseCallback = Callable[[], None]


async def periodic_cleanup_loop(interval_seconds: float, cleanup: CleanupCallback) -> None:
    """按固定间隔执行清理；同步文件操作在线程中运行，避免阻塞机器人。"""
    while True:
        await asyncio.sleep(interval_seconds)
        await asyncio.to_thread(cleanup)


def _task_is_active(value: object) -> bool:
    return isinstance(value, asyncio.Task) and not value.done()


async def start_managed_background_tasks(
    app: Any,
    *,
    cleanup_enabled: bool,
    cleanup: CleanupCallback,
    cleanup_loop: AsyncLoopFactory,
    remote_enabled: bool,
    remote_url: str,
    remote_probe_loop: AsyncLoopFactory,
) -> None:
    """启动唯一后台任务，重复初始化时不会创建第二份循环。"""
    if cleanup_enabled and not _task_is_active(app.bot_data.get("server_file_cleanup_task")):
        await asyncio.to_thread(cleanup)
        app.bot_data["server_file_cleanup_task"] = asyncio.create_task(cleanup_loop())
    if remote_enabled and remote_url and not _task_is_active(app.bot_data.get("remote_ocr_probe_task")):
        app.bot_data["remote_ocr_probe_task"] = asyncio.create_task(remote_probe_loop())


async def _cancel_task(value: object) -> None:
    if not isinstance(value, asyncio.Task):
        return
    value.cancel()
    try:
        await value
    except asyncio.CancelledError:
        pass


async def stop_managed_background_tasks(
    app: Any,
    *,
    close_callbacks: tuple[CloseCallback, ...] = (),
) -> None:
    """停止后台循环并释放复用的 HTTP 客户端。"""
    await _cancel_task(app.bot_data.pop("server_file_cleanup_task", None))
    await _cancel_task(app.bot_data.pop("remote_ocr_probe_task", None))
    for callback in close_callbacks:
        callback()
