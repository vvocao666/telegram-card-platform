# 01 Card OCR Only

Purpose: recognize PUBG/PSN card images and reply with card codes in the chat. This pack does not require secondary bot forwarding.

Current included behavior:

- PUBG card recognition.
- PSN card recognition.
- Batch image handling.
- Strict PUBG/PSN card length rules.
- Duplicate detection and "today duplicate" output.
- OCR correction/learning support.
- Fuzzy conflict output.
- Text card parsing.
- HTML/code-block formatting for easy copy.
- Ignores images with no card content.

Source snapshot:

- `source/bot.py`
- `source/test_bot.py`
- `source/requirements.txt`
- `source/.env.example`

Important config:

- `BOT_TOKEN`: main bot token.
- `OWNER_CHAT_ID`: owner ID, optional.
- `AUDIT_BOT_TOKEN`: leave empty for this pack.
- `AUDIT_CHAT_ID`: leave empty for this pack.
- OCR config keys in `.env.example`.

Integration notes:

- Keep `handle_photo`, OCR helpers, card parsing helpers, duplicate history helpers, correction-learning helpers, and reply formatting helpers from `bot.py`.
- Register `MessageHandler(filters.PHOTO, handle_photo)`.
- Register `MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ledger_text)` only if you also want text card parsing/correction learning; otherwise split the card text/correction part into a smaller text handler.
