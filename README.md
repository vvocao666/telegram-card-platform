# Telegram Card Platform

Current framework version: `telegram-card-platform-modular`

Stable rollback baseline: `strict-v120-owner-broadcast-no-trx`

Telegram Card Platform is a reusable Telegram bot framework for card OCR workflows. The v1.0 release packages the proven `strict-v120-owner-broadcast-no-trx` bot behavior into a modular structure for deployment, maintenance, and future extension.

The platform combines OCR, card parsing, audit forwarding, ledger/accounting, owner broadcast, admin checks, storage, CI, backup, rollback, and systemd deployment.

## Current Features

- PUBG/PSN card OCR from images.
- Forwarded image and batch image recognition.
- OCR.space OCR with local OCR fallback support.
- OCR correction learning and persistent correction rules.
- Duplicate card reminders with first-seen source.
- Optional secondary audit bot forwarding.
- Ledger/accounting for RMB income and USDT payout.
- Ledger bill buttons, clear, pause/open, daily cutover, and group owner permissions.
- OKX USDT/CNY price query.
- USDT-TRC20 verification image generation.
- Owner-only group broadcast.
- Runtime cleanup, rate limiting, systemd service, and backup scripts.

## Documents

- `ARCHITECTURE.md`: current architecture scan and proposed module split.
- `ROADMAP.md`: phased refactor plan.
- `DEPLOY.md`: new server deployment guide.
- `MAINTENANCE.md`: routine maintenance and rollback guide.
- `docs/CURRENT_FEATURES.md`: detailed feature inventory.
- `docs/REBUILD_GUIDE.md`: rebuild notes.
- `feature_backups/v120_stable/ROLLBACK.md`: restore guide for the last stable v120 version.

## Directory Structure

```text
bot.py                  # Application startup and handler registration
config/                 # Settings, logging, constants
handlers/               # Telegram Update handlers
services/               # OCR, ledger, broadcast, forward, price services
storage/                # Database/session/repositories
utils/                  # Shared utilities
tests/                  # Regression tests
scripts/                # Backup, deploy, restore helpers
systemd/                # Linux service templates
docs/                   # Feature and rebuild documentation
feature_backups/        # Stable rollback and feature backup files
```

## Quick Deploy

```bash
export APP_DIR=/opt/telegram-card-platform
sudo git clone https://github.com/vvocao666/telegram-card-platform.git "$APP_DIR"
cd "$APP_DIR"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git tesseract-ocr
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
cp .env.example .env
nano .env
sudo mkdir -p /etc/telegram-card-platform
printf 'APP_DIR=%s\nPYTHON_BIN=.venv/bin/python3\n' "$APP_DIR" | sudo tee /etc/telegram-card-platform/service.env
sudo cp systemd/telegram-card-platform.service /etc/systemd/system/telegram-card-platform.service
sudo systemctl daemon-reload
sudo systemctl enable telegram-card-platform
sudo systemctl start telegram-card-platform
sudo systemctl is-active telegram-card-platform
```

## Backup

Linux:

```bash
bash scripts/backup_data.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup.ps1
```

To include local `.env` in a private backup:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup.ps1 -IncludeEnv
```

## Restore

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore.ps1 -BackupDir .\backups\telegram-card-platform-YYYYMMDD-HHMMSS
```

To restore `.env` from a private backup:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore.ps1 -BackupDir .\backups\telegram-card-platform-YYYYMMDD-HHMMSS -IncludeEnv
```

On Linux, restore `.env` from a secure copy, restore `outputs/` if historical data is needed, then restart the service.

## Rollback

To restore the last stable v120 version, follow:

```text
feature_backups/v120_stable/ROLLBACK.md
```

The rollback copy restores the original `bot.py`, `ledger_commands.py`, `ledger_storage.py`, `.env.example`, and `requirements.txt`.

## Update

```bash
cd "$APP_DIR"
git pull --ff-only
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m py_compile bot.py services/ledger/ledger_commands.py storage/repositories/ledger_storage.py
sudo systemctl restart telegram-card-platform
```

## Logs

```bash
journalctl -u telegram-card-platform -f
journalctl -u telegram-card-platform --since "1 hour ago"
```

## Restart Service

```bash
sudo systemctl restart telegram-card-platform
sudo systemctl is-active telegram-card-platform
```

## Local Checks

```bash
python -m pytest
python -m py_compile bot.py services/runtime.py services/ledger/ledger_commands.py storage/repositories/ledger_storage.py
```
