from __future__ import annotations

import re
import sys

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from config.constants import BOT_VERSION, TEXT_ADD_GROUP, TEXT_LEDGER, TEXT_LEDGER_ADD_GROUP
from config.logging_config import configure_logging
from config.settings import load_settings
from handlers.admin_handler import show_id, show_version
from handlers.broadcast_handler import handle_broadcast_callback, start_broadcast
from handlers.card_ocr_handler import handle_photo
from handlers.ledger_handler import (
    handle_ledger_callback,
    handle_ledger_command,
    handle_ledger_menu,
    handle_new_chat_members,
    handle_priority_ledger_text,
)
from handlers.start_handler import handle_add_group_menu, start
import services.runtime as runtime
from services.runtime import *  # noqa: F403,F401 - compatibility exports for existing tests and external scripts.
from services.runtime import start_background_tasks, stop_background_tasks

if __name__ != "__main__":
    sys.modules[__name__] = runtime


def build_application() -> Application:
    settings = load_settings()
    if not settings.bot_token:
        raise RuntimeError("Please set BOT_TOKEN in .env first")

    request_kwargs = {
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
        .post_init(start_background_tasks)
        .post_shutdown(stop_background_tasks)
        .build()
    )
    register_handlers(app)
    return app


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("version", show_version))
    app.add_handler(
        MessageHandler(
            filters.Regex(f"^({re.escape(TEXT_LEDGER_ADD_GROUP)}|记账拉机器人进群)$"),
            handle_ledger_add_group_menu,
        )
    )
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(TEXT_LEDGER)}$"), handle_ledger_menu))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(TEXT_ADD_GROUP)}$"), handle_add_group_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^广播$") & filters.ChatType.PRIVATE, start_broadcast))
    app.add_handler(CallbackQueryHandler(handle_broadcast_callback, pattern=r"^broadcast:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_priority_ledger_text), group=-1)
    app.add_handler(
        CommandHandler(
            ["help", "bill", "fullbill", "yesterday", "undo", "clear", "in", "income", "out", "payout"],
            handle_ledger_command,
        )
    )
    app.add_handler(CallbackQueryHandler(handle_ledger_callback, pattern=r"^ledger:"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ledger_command))


def main() -> None:
    configure_logging()
    app = build_application()
    logger.info("Bot is starting. Version=%s.", BOT_VERSION)  # noqa: F405 - exported by services.runtime.
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
