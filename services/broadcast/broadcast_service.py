from __future__ import annotations

import html
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


UpdatePredicate = Callable[[Update | None], bool]
BroadcastTextExtractor = Callable[[str, str], str]


@dataclass(slots=True)
class BroadcastController:
    """封装 owner 私聊群广播流程，选择状态保存在 Telegram context 中。"""

    ledger_store: Any
    is_owner_update: UpdatePredicate
    is_private_update: UpdatePredicate
    extract_broadcast_text: BroadcastTextExtractor
    logger: logging.Logger

    def group_keyboard(self, selected: set[int] | None = None) -> InlineKeyboardMarkup:
        selected = selected or set()
        rows: list[list[InlineKeyboardButton]] = []
        for row in self.ledger_store.list_active_bot_groups():
            chat_id = int(row["chat_id"])
            title = row["title"] or str(chat_id)
            prefix = "√" if chat_id in selected else "□"
            rows.append([InlineKeyboardButton(f"{prefix} {title}", callback_data=f"broadcast:toggle:{chat_id}")])
        rows.append(
            [
                InlineKeyboardButton("下一步", callback_data="broadcast:next"),
                InlineKeyboardButton("取消", callback_data="broadcast:cancel"),
            ]
        )
        return InlineKeyboardMarkup(rows)

    def selected_titles(self, selected: set[int]) -> list[str]:
        groups = {
            int(row["chat_id"]): (row["title"] or str(row["chat_id"]))
            for row in self.ledger_store.list_active_bot_groups()
        }
        return [groups.get(chat_id, str(chat_id)) for chat_id in sorted(selected)]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not self.is_private_update(update):
            return
        if not self.is_owner_update(update):
            await update.message.reply_text("无权限。")
            return
        groups = self.ledger_store.list_active_bot_groups()
        if not groups:
            await update.message.reply_text("还没有记录到可广播的群。请先让机器人加入群，并让群里产生一条消息。")
            return
        context.user_data["broadcast_selected"] = set()
        context.user_data["broadcast_waiting_text"] = False
        context.user_data.pop("broadcast_pending_text", None)
        await update.message.reply_text("请选择要广播的群：", reply_markup=self.group_keyboard(set()))

    async def preview(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not self.is_private_update(update):
            return
        if not self.is_owner_update(update):
            await update.message.reply_text("无权限。")
            return
        selected = context.user_data.get("broadcast_selected")
        if not isinstance(selected, set) or not selected:
            await update.message.reply_text("请先使用 /broadcast 或“广播”选择要广播的群。")
            return
        text = self.extract_broadcast_text(update.message.text or "", "/broadcast_preview")
        if text:
            context.user_data["broadcast_pending_text"] = text
        text = str(context.user_data.get("broadcast_pending_text") or "")
        if not text:
            await update.message.reply_text("当前没有可预览的广播内容。")
            return
        titles = "\n".join(f"- {html.escape(title)}" for title in self.selected_titles(selected))
        await update.message.reply_text(
            f"广播目标：\n{titles}\n\n广播内容：\n{html.escape(text)}",
            parse_mode=ParseMode.HTML,
        )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not self.is_private_update(update):
            return
        if not self.is_owner_update(update):
            await update.message.reply_text("无权限。")
            return
        self._clear_pending(context)
        await update.message.reply_text("已取消广播。")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        if not self.is_owner_update(update):
            await query.edit_message_text("无权限。")
            return
        data = query.data or ""
        selected = context.user_data.get("broadcast_selected")
        if not isinstance(selected, set):
            selected = set()
        if data == "broadcast:cancel":
            self._clear_pending(context)
            await query.edit_message_text("已取消广播。")
            return
        if data == "broadcast:next":
            if not selected:
                await query.edit_message_text("请至少选择一个群。", reply_markup=self.group_keyboard(selected))
                return
            context.user_data["broadcast_selected"] = selected
            context.user_data["broadcast_waiting_text"] = True
            await query.edit_message_text("请输入要广播的内容。")
            return
        if data == "broadcast:confirm":
            await self._confirm(query, context, selected)
            return
        match = re.fullmatch(r"broadcast:toggle:(-?\d+)", data)
        if match:
            chat_id = int(match.group(1))
            if chat_id in selected:
                selected.remove(chat_id)
            else:
                selected.add(chat_id)
            context.user_data["broadcast_selected"] = selected
            await query.edit_message_reply_markup(reply_markup=self.group_keyboard(selected))

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if not update.message or not self.is_private_update(update) or not self.is_owner_update(update):
            return False
        if not context.user_data.get("broadcast_waiting_text"):
            return False
        text = update.message.text or ""
        if text.strip() in {"取消", "取消广播", "/broadcast_cancel"}:
            self._clear_pending(context)
            await update.message.reply_text("已取消广播。")
            return True
        selected = context.user_data.get("broadcast_selected")
        if not isinstance(selected, set) or not selected:
            context.user_data.pop("broadcast_waiting_text", None)
            await update.message.reply_text("没有选择群，请重新发送 /broadcast。")
            return True
        context.user_data["broadcast_pending_text"] = text
        titles = "\n".join(f"- {html.escape(title)}" for title in self.selected_titles(selected))
        preview = f"广播目标：\n{titles}\n\n广播内容：\n{html.escape(text)}"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("确认发送", callback_data="broadcast:confirm"), InlineKeyboardButton("取消", callback_data="broadcast:cancel")]]
        )
        await update.message.reply_text(preview, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return True

    async def _confirm(self, query: Any, context: ContextTypes.DEFAULT_TYPE, selected: set[int]) -> None:
        text = str(context.user_data.get("broadcast_pending_text") or "")
        if not selected or not text:
            await query.edit_message_text("广播任务已失效，请重新发送 /broadcast。")
            return
        started_at = time.monotonic()
        success = 0
        failed = 0
        for chat_id in sorted(selected):
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
                success += 1
            except Exception:
                self.logger.exception("Broadcast to chat %s failed", chat_id)
                failed += 1
        self._clear_pending(context)
        await query.edit_message_text(f"广播完成\n成功：{success}\n失败：{failed}\n耗时：{time.monotonic() - started_at:.2f}秒")

    @staticmethod
    def _clear_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data.pop("broadcast_selected", None)
        context.user_data.pop("broadcast_waiting_text", None)
        context.user_data.pop("broadcast_pending_text", None)
