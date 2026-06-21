# Maintenance Guide

Current framework version: `telegram-card-platform-modular`

Stable rollback baseline: `strict-v120-owner-broadcast-no-trx`

## Daily Checks

```bash
systemctl is-active telegram-card-platform
journalctl -u telegram-card-platform --since "1 hour ago"
```

## Safe Change Rules

- Do not commit `.env`, databases, logs, runtime outputs, or backups.
- Run tests before committing.
- Keep `bot.py` behavior unchanged until a refactor phase is explicitly approved.
- Move code in small batches and keep rollback easy.

## Test Commands

```bash
python -m pytest
python -m py_compile bot.py services/runtime.py services/ledger/ledger_commands.py storage/repositories/ledger_storage.py
```

## Backup Before Changes

Linux:

```bash
bash scripts/backup_data.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup.ps1
```

For a full local source backup, copy the project while excluding:

- `.git`
- `.env`
- `.venv`
- `outputs/`
- `backups/`
- `__pycache__/`
- `.pytest_cache/`

## Restore

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore.ps1 -BackupDir .\backups\telegram-card-platform-YYYYMMDD-HHMMSS
```

Linux restore should copy back `.env` and `outputs/`, then restart:

```bash
sudo systemctl restart telegram-card-platform
```

## Common Issues

- Bot does not start: check `BOT_TOKEN`, Python dependencies, service env file, and `journalctl -u telegram-card-platform`.
- OCR fails: check OCR API key, network access, image size limits, and OCR cooldown logs.
- Ledger data missing: check `LEDGER_DB_PATH` and restored database file ownership.
- Broadcast group missing: let the bot observe a message in that group so it can record the group.

## Rollback

```bash
cd "$APP_DIR"
git log --oneline -5
git checkout <known-good-commit>
sudo systemctl restart telegram-card-platform
```

Use rollback only after confirming which commit is the known-good baseline.

For the last stable v120 file-level rollback, use `feature_backups/v120_stable/ROLLBACK.md`.
