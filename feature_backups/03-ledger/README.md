# 03 Ledger

Purpose: accounting/ledger commands for groups and private chats.

Current included behavior:

- `+100`, `-100`, and continuous arithmetic expression handling.
- Rate divisor: `设置汇率10` means `+1000/10 = 100 U`.
- Bills: today, yesterday, full bill.
- Clear bill.
- Pause/open ledger: `暂停`, `开启`, `暂停记账`, `开启记账`, `关闭记账`.
- Daily cutover: `日切几点`; default is 00:00.
- Group owner permission: the user who invited the bot controls clear/pause/cutover operations.
- Inline bill buttons.
- SQLite storage.

Source snapshot:

- `source/ledger_commands.py`
- `source/ledger_storage.py`
- `source/bot.py`
- `source/test_bot.py`
- `source/requirements.txt`

Important config:

- `LEDGER_DB_PATH`: defaults to `outputs/ledger.sqlite3`.
- `OWNER_CHAT_ID`: fallback owner ID.

Integration notes:

- For a new ledger-only bot, keep `ledger_commands.py`, `ledger_storage.py`, and the ledger-related functions from `bot.py`: `ledger_keyboard`, `ledger_actor`, `remember_ledger_user`, `ensure_private_ledger_owner`, `reply_ledger`, `handle_ledger_text`, `handle_ledger_callback`, and `handle_new_chat_members`.
- Register ledger command handlers, callback handler with pattern `^ledger:`, text handler, and new-chat-members handler.
