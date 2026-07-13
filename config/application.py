from __future__ import annotations

from collections.abc import Callable
from typing import Any

from telegram.ext import Application
from telegram.request import HTTPXRequest

from config.settings import load_settings


def build_telegram_application(
    *,
    register_handlers: Callable[[Application], None],
    post_init: Callable[[Application], Any],
    post_shutdown: Callable[[Application], Any],
) -> Application:
    """根据统一配置创建 Telegram Application，避免入口配置发生漂移。"""
    settings = load_settings()
    if not settings.bot_token:
        raise RuntimeError("Please set BOT_TOKEN in .env first")

    request_kwargs: dict[str, object] = {
        "connect_timeout": settings.telegram_timeout,
        "read_timeout": settings.telegram_timeout,
        "write_timeout": settings.telegram_timeout,
        "pool_timeout": settings.telegram_timeout,
    }
    if settings.proxy_url:
        request_kwargs["proxy_url"] = settings.proxy_url

    app = (
        Application.builder()
        .token(settings.bot_token)
        .request(HTTPXRequest(**request_kwargs))
        .get_updates_request(HTTPXRequest(**request_kwargs))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    register_handlers(app)
    return app
