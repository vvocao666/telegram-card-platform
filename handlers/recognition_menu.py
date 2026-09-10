from __future__ import annotations

import re
import secrets

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop

from handlers.admin_handler import is_owner_update
from services import runtime
from services.broadcast.broadcast_service import group_selection_keyboard


COMMAND_PATTERN = r"^/(关闭识别|开启识别)(?:@\w+)?\s*$"
PAGE_SIZE = 20


def selection_keyboard(state):
    prefix = "recognition:" + state["token"]
    page = state["page"]
    rows = list(group_selection_keyboard(
        state["groups"][page * PAGE_SIZE:(page + 1) * PAGE_SIZE], state["selected"], prefix,
    ).inline_keyboard)
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton("上一页", callback_data=f"{prefix}:page:{page - 1}"))
    if (page + 1) * PAGE_SIZE < len(state["groups"]):
        navigation.append(InlineKeyboardButton("下一页", callback_data=f"{prefix}:page:{page + 1}"))
    if navigation:
        rows.insert(-1, navigation)
    return InlineKeyboardMarkup(rows)


def selection_text(state):
    action = "开启" if state["enabled"] else "关闭"
    return f"请选择要{action}卡密识别的群（可多选，已选 {len(state['selected'])} 个）：\n确认后生效，群内不发送提醒。"


async def handle_recognition_command(update, context):
    if not update.message or not update.effective_chat or update.effective_chat.type != "private":
        return
    match = re.fullmatch(COMMAND_PATTERN, update.message.text or "")
    if not match:
        return
    if not is_owner_update(update):
        await update.message.reply_text("只有机器人主人可以管理群识别开关。", do_quote=False)
        raise ApplicationHandlerStop
    context.user_data.pop("recognition_selection", None)
    enabled = match.group(1) == "开启识别"
    groups = [
        dict(row) for row in runtime.ledger_store.list_active_bot_groups()
        if runtime.ledger_store.is_recognition_enabled(int(row["chat_id"])) != enabled
    ]
    if not groups:
        text = "目前没有已关闭卡密识别的群。" if enabled else "目前没有可关闭卡密识别的群。"
        await update.message.reply_text(text, do_quote=False)
        raise ApplicationHandlerStop
    state = {
        "token": secrets.token_hex(4), "enabled": enabled, "groups": groups,
        "selected": set(), "page": 0, "stage": "select",
    }
    sent = await update.message.reply_text(selection_text(state), reply_markup=selection_keyboard(state), do_quote=False)
    state["message_id"] = sent.message_id
    context.user_data["recognition_selection"] = state
    raise ApplicationHandlerStop


async def handle_recognition_callback(update, context):
    query = update.callback_query
    if not query:
        return
    if not is_owner_update(update) or not update.effective_chat or update.effective_chat.type != "private":
        await query.answer("无权限。", show_alert=True)
        return
    state = context.user_data.get("recognition_selection")
    parts = (query.data or "").split(":")
    if (
        not state or len(parts) < 3 or parts[:2] != ["recognition", state["token"]]
        or query.message is None or query.message.message_id != state["message_id"]
    ):
        await query.answer("这个菜单已失效，请重新发送识别开关指令。", show_alert=True)
        return
    await query.answer()
    action = parts[2]
    if action == "cancel":
        context.user_data.pop("recognition_selection", None)
        await query.edit_message_text("已取消。")
        return
    if action == "back":
        state["stage"] = "select"
    elif action in {"toggle", "page"} and state["stage"] == "select" and len(parts) == 4:
        try:
            value = int(parts[3])
        except ValueError:
            return
        if action == "toggle":
            if value not in {int(row["chat_id"]) for row in state["groups"]}:
                return
            state["selected"].symmetric_difference_update({value})
        elif 0 <= value <= (len(state["groups"]) - 1) // PAGE_SIZE:
            state["page"] = value
    elif action == "next" and state["stage"] == "select":
        if not state["selected"]:
            return
        state["stage"] = "confirm"
        label = "开启" if state["enabled"] else "关闭"
        names = "\n".join(str(row["title"] or row["chat_id"]) for row in state["groups"] if int(row["chat_id"]) in state["selected"])
        prefix = "recognition:" + state["token"]
        await query.edit_message_text(
            f"确认{label}以下 {len(state['selected'])} 个群的卡密识别？\n{names[:3000]}\n群内不发送提醒。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"确认{label}", callback_data=f"{prefix}:confirm")],
                [InlineKeyboardButton("返回", callback_data=f"{prefix}:back"), InlineKeyboardButton("取消", callback_data=f"{prefix}:cancel")],
            ]),
        )
        return
    elif action == "confirm" and state["stage"] == "confirm" and state["selected"]:
        context.user_data.pop("recognition_selection", None)
        active = {int(row["chat_id"]) for row in runtime.ledger_store.list_active_bot_groups()}
        changed = 0
        for row in state["groups"]:
            chat_id = int(row["chat_id"])
            if chat_id in state["selected"] and chat_id in active:
                runtime.ledger_store.set_recognition_enabled(chat_id, state["enabled"], silent=True)
                changed += 1
        label = "开启" if state["enabled"] else "关闭"
        await query.edit_message_text(f"已{label} {changed} 个群的卡密识别。")
        return
    else:
        return
    await query.edit_message_text(selection_text(state), reply_markup=selection_keyboard(state))
