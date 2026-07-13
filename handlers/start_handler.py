from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config.constants import TEXT_LEDGER_ADD_GROUP
from services.ledger import ledger_commands


def start_help_text() -> str:
    return ledger_commands.HELP_TEXT


def add_group_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    add_group_url = f"https://t.me/{bot_username}?startgroup=true" if bot_username else "https://t.me/"
    return InlineKeyboardMarkup([[InlineKeyboardButton("➕ 拉机器人进群", url=add_group_url)]])


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[TEXT_LEDGER_ADD_GROUP]], resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            start_help_text(),
            reply_markup=main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def handle_add_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    bot_user = await context.bot.get_me()
    await update.message.reply_text(
        "🤖 点击下方按钮拉机器人进群。",
        reply_markup=add_group_keyboard(bot_user.username or ""),
    )
