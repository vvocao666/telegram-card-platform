# 05 TRC20 Anti-Tamper Image

Purpose: when a user sends a USDT-TRC20 address, generate an anti-tamper verification image with generation time.

Current included behavior:

- Detects TRON/TRC20 address text.
- Generates a verification image.
- Adds generation time.
- Sends the original address text with the image so users can copy/check.

Source snapshot:

- `source/bot.py`
- `source/test_bot.py`
- `source/requirements.txt`

Important config:

- `BOT_TOKEN`: bot token.
- PIL/Pillow dependency from `requirements.txt`.

Integration notes:

- Keep `extract_trc20_address`, image drawing helpers, and `reply_trc20_verify_image` from `bot.py`.
- Register a text handler and check TRC20 address before ledger or generic text handling if the new bot should prioritize address images.
