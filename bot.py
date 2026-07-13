from __future__ import annotations

import sys

from telegram import Update
from telegram.ext import Application

from config.application import build_telegram_application
from config.constants import BOT_VERSION
from config.logging_config import configure_logging
from handlers.registry import register_handlers
import services.runtime as runtime
from services.runtime import *  # noqa: F403,F401 - compatibility exports for existing tests and external scripts.
from services.runtime import start_background_tasks, stop_background_tasks

if __name__ != "__main__":
    sys.modules[__name__] = runtime


def build_application() -> Application:
    return build_telegram_application(
        register_handlers=register_handlers,
        post_init=start_background_tasks,
        post_shutdown=stop_background_tasks,
    )


def main() -> None:
    configure_logging()
    app = build_application()
    logger.info("Bot is starting. Version=%s.", BOT_VERSION)  # noqa: F405 - exported by services.runtime.
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
