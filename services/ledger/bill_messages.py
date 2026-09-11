from __future__ import annotations

from telegram.error import BadRequest


async def send_bill(message, chunks, reply_markup, store):
    root_id = None
    for index, chunk in enumerate(chunks):
        sent = await message.reply_text(
            chunk, do_quote=False, reply_markup=reply_markup if index == 0 else None,
            parse_mode="HTML", disable_web_page_preview=True,
        )
        if index == 0:
            root_id = sent.message_id
        elif reply_markup is not None:
            store.remember_bill_page(message.chat_id, root_id, sent.message_id)


async def _edit(edit, **kwargs):
    try:
        await edit(**kwargs)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def replace_bill(query, chunks, reply_markup, store):
    chat_id, root_id = query.message.chat_id, query.message.message_id
    bot = query.get_bot()
    pages = store.bill_pages(chat_id, root_id)
    await _edit(query.edit_message_text, text=chunks[0], reply_markup=reply_markup,
                parse_mode="HTML", disable_web_page_preview=True)
    for page_id in pages:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=page_id)
        except BadRequest as exc:
            if "message to delete not found" not in str(exc).lower():
                # Old messages may be outside Telegram's deletion window; hide their rows by editing.
                await _edit(bot.edit_message_text, chat_id=chat_id, message_id=page_id, text="—")
        store.forget_bill_page(chat_id, root_id, page_id)
    for chunk in chunks[1:]:
        sent = await query.message.reply_text(
            chunk, do_quote=False, parse_mode="HTML", disable_web_page_preview=True,
        )
        store.remember_bill_page(chat_id, root_id, sent.message_id)
