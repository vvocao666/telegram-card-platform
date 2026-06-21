# Release v1.0.0

Release name: Telegram Card Platform v1.0.0

Stable baseline: `strict-v120-owner-broadcast-no-trx`

## Included Capabilities

- OCR: OCR.space integration, local OCR fallback hooks, image preparation, batching, cleanup, and rate limiting.
- PUBG: strict PUBG card validation and extraction rules.
- PSN: strict PSN card validation and extraction rules.
- Broadcast: owner-only group broadcast flow.
- Ledger: RMB income, USDT payout, bills, clear, pause/open, daily cutover, exchange-rate settings, and group-owner permissions.
- Forward: secondary audit bot forwarding with source metadata and photo fallback handling.
- Admin: owner checks, `/id`, `/version`, and permission helpers.
- Storage: SQLite-backed ledger, card history, correction learning, user/group records, and bot group records.
- CI: GitHub Actions workflow for compile and test.
- Backup: Linux data backup script and Windows PowerShell project backup.
- Rollback: v120 stable files and rollback guide under `feature_backups/v120_stable/`.

## Verification

- `python -m pytest`
- `python -m compileall -q bot.py config handlers services storage utils tests`

## Deployment

Use `DEPLOY.md` for Ubuntu 22.04, Ubuntu 24.04, and Debian 12 deployment.

## Rollback

Use `feature_backups/v120_stable/ROLLBACK.md` to restore the last stable online version.
