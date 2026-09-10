from __future__ import annotations

import asyncio
import logging
import secrets

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from handlers.admin_handler import is_owner_update
from handlers.message_cleanup_handler import enqueue_group_cleanup
from services import runtime
from services.broadcast.broadcast_service import group_selection_keyboard
from services.group.message_cleanup import can_delete_group_messages


logger = logging.getLogger(__name__)
PAGE_SIZE = 20


def selection_keyboard(state):
    prefix = "cleanup:" + state["token"]
    page = state["page"]
    groups = state["groups"][page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    rows = list(group_selection_keyboard(groups, state["selected"], prefix).inline_keyboard)
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton("上一页", callback_data=f"{prefix}:page:{page - 1}"))
    if (page + 1) * PAGE_SIZE < len(state["groups"]):
        navigation.append(InlineKeyboardButton("下一页", callback_data=f"{prefix}:page:{page + 1}"))
    if navigation:
        rows.insert(-1, navigation)
    return InlineKeyboardMarkup(rows)


def selection_text(state):
    return (
        f"请选择要清理消息的群（可多选，已选 {len(state['selected'])} 个）：\n"
        "仅清理未满 48 小时的可删除消息，群内不发送提醒。\n"
        "尚无消息记录的群，需要先在群里发一条消息。"
    )


def bounded_lines(lines):
    result = []
    length = 0
    for line in lines:
        if length + len(line) > 3000:
            result.append("……内容较多，返回群列表可查看全部已选群。")
            break
        result.append(line)
        length += len(line) + 1
    return "\n".join(result)


async def start_cleanup_menu(update, context):
    if not is_owner_update(update):
        await update.message.reply_text("只有机器人主人可以使用 /del。", do_quote=False)
        return
    groups = [dict(row) for row in runtime.ledger_store.list_active_bot_groups()]
    if not groups:
        await update.message.reply_text("还没有记录到群。请先让机器人加入群，并让群里产生一条消息。", do_quote=False)
        return
    state = {"token": secrets.token_hex(4), "groups": groups, "selected": set(), "page": 0, "stage": "select"}
    sent = await update.message.reply_text(selection_text(state), reply_markup=selection_keyboard(state), do_quote=False)
    state["message_id"] = sent.message_id
    context.user_data["cleanup_selection"] = state


async def handle_cleanup_callback(update, context):
    query = update.callback_query
    if query is None:
        return
    if not is_owner_update(update) or not update.effective_chat or update.effective_chat.type != "private":
        await query.answer("无权限。", show_alert=True)
        return
    state = context.user_data.get("cleanup_selection")
    parts = (query.data or "").split(":")
    if (
        not state or len(parts) < 3 or parts[:2] != ["cleanup", state["token"]]
        or query.message is None or query.message.message_id != state["message_id"]
    ):
        await query.answer("这个菜单已失效，请重新发送 /del。", show_alert=True)
        return
    action = parts[2]
    await query.answer()
    if action == "cancel":
        context.user_data.pop("cleanup_selection", None)
        await query.edit_message_text("已取消清理。")
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
            await query.edit_message_text("请至少选择一个群。", reply_markup=selection_keyboard(state))
            return
        state["stage"] = "confirm"
        titles = bounded_lines(
            "• " + (row["title"] or str(row["chat_id"]))
            for row in state["groups"] if int(row["chat_id"]) in state["selected"]
        )
        prefix = "cleanup:" + state["token"]
        await query.edit_message_text(
            f"将清理以下 {len(state['selected'])} 个群未满 48 小时的可删除消息：\n{titles}\n\n删除后无法恢复。",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("确认清理", callback_data=f"{prefix}:confirm"),
                InlineKeyboardButton("返回", callback_data=f"{prefix}:back"),
                InlineKeyboardButton("取消", callback_data=f"{prefix}:cancel"),
            ]]),
        )
        return
    elif action == "confirm" and state["stage"] == "confirm" and state["selected"]:
        positions = context.bot_data.get("group_message_positions")
        if positions is None:
            await query.edit_message_text("消息记录暂不可用，请稍后重新发送 /del。")
            context.user_data.pop("cleanup_selection", None)
            return
        groups = [row for row in state["groups"] if int(row["chat_id"]) in state["selected"]]
        limits = {int(row["chat_id"]): positions.latest(int(row["chat_id"])) for row in groups}
        context.user_data.pop("cleanup_selection", None)
        await query.edit_message_text(f"正在清理已选的 {len(groups)} 个群，结果会显示在这里。")
        tasks = context.bot_data.setdefault("private_message_cleanup_tasks", {})
        tasks[state["token"]] = asyncio.create_task(run_selected_cleanup(query, context, state["token"], groups, limits))
        return
    else:
        return
    await query.edit_message_text(selection_text(state), reply_markup=selection_keyboard(state))


async def run_selected_cleanup(query, context, token, groups, limits):
    semaphore = asyncio.Semaphore(3)

    async def clean(row):
        chat_id = int(row["chat_id"])
        title = row["title"] or str(chat_id)
        async with semaphore:
            if not limits[chat_id]:
                return False, f"{title}：尚无消息记录，请先在群里发一条消息。"
            try:
                member = await context.bot.get_chat_member(chat_id, context.bot.id)
                if not can_delete_group_messages(member, row["chat_type"]):
                    return False, f"{title}：机器人没有删除权限。"
                task = enqueue_group_cleanup(
                    context, chat_id, row["chat_type"], context.application.chat_data[chat_id], limits[chat_id],
                )
                if await task:
                    return True, ""
                return False, f"{title}：清理中断，部分消息可能已删除。"
            except TelegramError:
                return False, f"{title}：无法访问群或确认权限。"

    try:
        results = await asyncio.gather(*(clean(row) for row in groups))
        succeeded = sum(ok for ok, _ in results)
        details = bounded_lines(text for ok, text in results if not ok)
        await query.edit_message_text(
            f"本次清理结束：完成 {succeeded} 个群，未完成 {len(results) - succeeded} 个群。\n"
            "超过 48 小时及不可删除的消息保留。" + ("\n\n" + details if details else "")
        )
    except TelegramError:
        logger.warning("Could not update private cleanup result")
    finally:
        context.bot_data.get("private_message_cleanup_tasks", {}).pop(token, None)
