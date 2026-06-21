# 04 OKX Price

Purpose: query OKX USDT/CNY prices.

Current included behavior:

- Commands/text: `币价`, `bj`, any case variant of `bj`.
- Fetches latest OKX C2C USDT/CNY sell-side prices.
- Shows latest 5 prices.
- Falls back to OKX official USD/CNY exchange rate if C2C fetch fails.

Source snapshot:

- `source/bot.py`
- `source/test_bot.py`
- `source/requirements.txt`

Important config:

- No special token besides `BOT_TOKEN`.
- Uses `OKX_C2C_USDT_CNY_URL` and `OKX_EXCHANGE_RATE_URL` constants in `bot.py`.

Integration notes:

- Keep `is_price_command`, `fetch_okx_usdt_cny_prices`, `format_okx_prices`, `reply_okx_price`, and OKX parse helpers from `bot.py`.
- In a new bot, route text messages matching `币价` or `bj` to `reply_okx_price`.
