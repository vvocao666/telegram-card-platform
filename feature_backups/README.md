# Feature Backups

This directory stores reusable feature packs from the current Telegram bot.

The removed payment add-on is not included in this repository.

Feature packs:

1. `01-card-ocr-only`: card OCR reply only, no audit forwarding.
2. `02-card-ocr-audit-forward`: card OCR reply plus secondary audit bot forwarding.
3. `03-ledger`: ledger/accounting commands and storage.
4. `04-okx-price`: OKX USDT/CNY price query.
5. `05-trc20-anti-tamper`: USDT-TRC20 address anti-tamper image generation.

These packs are snapshots, not independent pip packages. When creating a new bot, copy the needed source files and follow the README for the selected pack.

## Current Standards

- Card OCR packs include correction learning, persistent OCR fixes, duplicate reminders, and silent handling for non-card images.
- Ledger pack uses the latest RMB income / USDT payout logic.
- Price pack supports `币价`, `bj`, `z0`, and `Z0`.
