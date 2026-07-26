from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class LedgerTextHooks:
    store: Any
    remember_bot_chat: Callable[[Any], None]
    remember_ledger_user: Callable[[Any], None]
    ensure_private_owner: Callable[[Any], None]
    owner_ids: Callable[[int | None], set[int]]
    extract_trc20_address: Callable[[str], str | None]
    reply_trc20_verify_image: Callable[[Any, str], Awaitable[None]]
    set_realtime_rate: Callable[[Any], Awaitable[bool]]
    is_price_command: Callable[[str], bool]
    reply_okx_price: Callable[[Any], Awaitable[None]]
    calculate_expression: Callable[[str], str | None]
    actor_from_update: Callable[[Any], Any]
    actor_from_message: Callable[[Any], Any | None]
    handle_command_text: Callable[..., Any]
    reply_ledger: Callable[[Any, str], Awaitable[None]]


async def handle_ledger_text(
    update: Any,
    hooks: LedgerTextHooks,
    *,
    allow_trc20: bool = True,
) -> bool:
    if not update.message or not update.effective_chat:
        return False
    hooks.remember_bot_chat(update)
    hooks.remember_ledger_user(update)
    hooks.ensure_private_owner(update)
    text = update.message.text or ""
    normalized_text = text.strip()
    if normalized_text in {"开启识别", "打开识别", "启用识别"}:
        if update.effective_user and update.effective_user.id not in hooks.owner_ids(update.effective_chat.id):
            await update.message.reply_text("只有拉机器人进群的人可以开启识别。")
            return True
        hooks.store.set_recognition_enabled(update.effective_chat.id, True)
        await update.message.reply_text("卡密识别已开启。")
        return True
    if normalized_text in {"关闭识别", "停止识别", "停用识别", "暂停识别"}:
        if update.effective_user and update.effective_user.id not in hooks.owner_ids(update.effective_chat.id):
            await update.message.reply_text("只有拉机器人进群的人可以关闭识别。")
            return True
        hooks.store.set_recognition_enabled(update.effective_chat.id, False)
        await update.message.reply_text("卡密识别已关闭，后续图片不会识别卡密。发送“开启识别”可重新开启。")
        return True
    trc20_address = hooks.extract_trc20_address(text) if allow_trc20 else None
    if trc20_address:
        await hooks.reply_trc20_verify_image(update.message, trc20_address)
        return True
    if await hooks.set_realtime_rate(update):
        return True
    if hooks.is_price_command(text):
        await hooks.reply_okx_price(update.message)
        return True
    calculation = hooks.calculate_expression(text)
    if calculation is not None:
        await update.message.reply_text(calculation)
        return True

    reply_message = update.message.reply_to_message
    reply_user = hooks.actor_from_message(reply_message) if reply_message else None
    reply_text = reply_message.text or reply_message.caption if reply_message else None
    reply_message_id = reply_message.message_id if reply_message else None
    result = hooks.handle_command_text(
        store=hooks.store,
        chat_id=update.effective_chat.id,
        actor=hooks.actor_from_update(update),
        text=text,
        owner_ids=hooks.owner_ids(update.effective_chat.id),
        reply_user=reply_user,
        reply_text=reply_text,
        message_id=update.message.message_id,
        reply_message_id=reply_message_id,
    )
    if result:
        await hooks.reply_ledger(update.message, result.text)
        if result.follow_up_text:
            await update.message.reply_text(result.follow_up_text)
        return True
    return False
