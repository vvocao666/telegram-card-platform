from __future__ import annotations

import re

from telegram.ext import Application, CallbackQueryHandler, ChatMemberHandler, CommandHandler, MessageHandler, filters

from config.constants import TEXT_ADD_GROUP, TEXT_LEDGER, TEXT_LEDGER_ADD_GROUP
from handlers.admin_handler import (
    learn_cancel_command,
    learn_cards_command,
    learn_confirm_command,
    ocr_candidates_command,
    ocr_cache_today_command,
    ocr_debug_command,
    ocr_export_fonts_command,
    ocr_font_stats_command,
    ocr_health_command,
    ocr_import_fonts_command,
    ocr_learning_stats_command,
    ocr_review_command,
    ocr_version_command,
    remote_ocr_status_command,
    show_id,
    show_version,
    status_panel_command,
)
from handlers.broadcast_handler import (
    broadcast_cancel_command,
    broadcast_preview_command,
    handle_broadcast_callback,
    notify_all_command,
    notify_members_command,
    start_broadcast,
)
from handlers.card_ocr_handler import handle_photo
from handlers.ledger_handler import (
    handle_bot_chat_member,
    handle_class_mode_command,
    handle_class_mode_notice_once,
    handle_ledger_add_group_menu,
    handle_ledger_callback,
    handle_ledger_command,
    handle_ledger_menu,
    handle_new_chat_members,
    handle_priority_ledger_text,
)
from handlers.start_handler import handle_add_group_menu, start


def register_handlers(app: Application) -> None:
    """集中维护生产 handler 顺序；顺序本身属于行为契约。"""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("version", show_version))
    app.add_handler(CommandHandler("ocr_debug", ocr_debug_command))
    app.add_handler(CommandHandler("ocr_candidates", ocr_candidates_command))
    app.add_handler(CommandHandler("ocr_font_stats", ocr_font_stats_command))
    app.add_handler(CommandHandler("ocr_review", ocr_review_command))
    app.add_handler(CommandHandler("ocr_export_fonts", ocr_export_fonts_command))
    app.add_handler(CommandHandler("ocr_import_fonts", ocr_import_fonts_command))
    app.add_handler(CommandHandler("ocr_version", ocr_version_command))
    app.add_handler(CommandHandler("ocr_cache_today", ocr_cache_today_command))
    app.add_handler(CommandHandler("ocr_health", ocr_health_command))
    app.add_handler(CommandHandler("remote_ocr_status", remote_ocr_status_command))
    app.add_handler(CommandHandler(["status", "ocr_status"], status_panel_command))
    app.add_handler(MessageHandler(filters.Regex(r"^/状态(?:@\w+)?(?:\s|$)"), status_panel_command))
    app.add_handler(CommandHandler("learn_cards", learn_cards_command))
    app.add_handler(MessageHandler(filters.Regex(r"^/?学习卡密(?:\s|$)") & filters.ChatType.PRIVATE, learn_cards_command))
    app.add_handler(CommandHandler("learn_confirm", learn_confirm_command))
    app.add_handler(CommandHandler("learn_cancel", learn_cancel_command))
    app.add_handler(CommandHandler("ocr_learning_stats", ocr_learning_stats_command))
    app.add_handler(
        MessageHandler(
            filters.Regex(f"^({re.escape(TEXT_LEDGER_ADD_GROUP)}|记账拉机器人进群)$"),
            handle_ledger_add_group_menu,
        )
    )
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(TEXT_LEDGER)}$"), handle_ledger_menu))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(TEXT_ADD_GROUP)}$"), handle_add_group_menu))
    app.add_handler(CommandHandler("broadcast", start_broadcast))
    app.add_handler(MessageHandler(filters.Regex(r"^广播$") & filters.ChatType.PRIVATE, start_broadcast))
    app.add_handler(CommandHandler("broadcast_preview", broadcast_preview_command))
    app.add_handler(CommandHandler("broadcast_cancel", broadcast_cancel_command))
    app.add_handler(CommandHandler(["notify_all", "at_all"], notify_all_command))
    app.add_handler(CommandHandler("notify_members", notify_members_command))
    app.add_handler(MessageHandler(filters.Regex(r"^通知所有人(?:\s|$)") & filters.ChatType.GROUPS, notify_all_command))
    app.add_handler(CallbackQueryHandler(handle_broadcast_callback, pattern=r"^broadcast:"))
    app.add_handler(MessageHandler(filters.Regex(r"^/(?:上课|下课)(?:@\w+)?\s*$"), handle_class_mode_command), group=-2)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, handle_class_mode_notice_once), group=-1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_priority_ledger_text), group=-1)
    app.add_handler(
        CommandHandler(
            [
                "help",
                "bill",
                "fullbill",
                "yesterday",
                "undo",
                "clear",
                "in",
                "income",
                "out",
                "payout",
                "set_cutoff",
                "cutoff",
            ],
            handle_ledger_command,
        )
    )
    app.add_handler(CallbackQueryHandler(handle_ledger_callback, pattern=r"^ledger:"))
    app.add_handler(ChatMemberHandler(handle_bot_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ledger_command))
