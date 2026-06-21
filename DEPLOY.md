# Deploy Guide

Current framework version: `telegram-card-platform-modular`

Stable rollback baseline: `strict-v120-owner-broadcast-no-trx`

## Server Requirements

- Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, or Debian 12.
- Python 3 with `venv`.
- Git.
- Tesseract OCR when local fallback is enabled.
- Systemd.

Supported release targets:

- Ubuntu 22.04
- Ubuntu 24.04
- Debian 12

## Install

Choose an application directory first:

```bash
export APP_DIR=/opt/telegram-card-platform
sudo git clone https://github.com/vvocao666/telegram-card-platform.git "$APP_DIR"
cd "$APP_DIR"
```

Install dependencies:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git tesseract-ocr
python3 -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.txt
```

## Configure

```bash
cp .env.example .env
nano .env
```

Required:

- `BOT_TOKEN`
- `OCR_SPACE_API_KEY` or `OCR_SPACE_API_KEYS`

Recommended:

- `OWNER_CHAT_ID`
- `AUDIT_BOT_TOKEN`
- `AUDIT_CHAT_ID`
- `LEDGER_DB_PATH`
- `PROXY_URL` when the server requires a proxy.

## Systemd

Create the service environment file:

```bash
sudo mkdir -p /etc/telegram-card-platform
printf 'APP_DIR=%s\nPYTHON_BIN=.venv/bin/python3\n' "$APP_DIR" | sudo tee /etc/telegram-card-platform/service.env
```

Install and start the service:

```bash
sudo cp systemd/telegram-card-platform.service /etc/systemd/system/telegram-card-platform.service
sudo systemctl daemon-reload
sudo systemctl enable telegram-card-platform
sudo systemctl start telegram-card-platform
sudo systemctl is-active telegram-card-platform
```

## Logs

```bash
journalctl -u telegram-card-platform -f
journalctl -u telegram-card-platform --since "1 hour ago"
```

## Update

```bash
cd "$APP_DIR"
git pull --ff-only
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m py_compile bot.py services/runtime.py services/ledger/ledger_commands.py storage/repositories/ledger_storage.py
sudo systemctl restart telegram-card-platform
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

## Restore

1. Deploy the code.
2. Restore `.env` from a secure copy.
3. Restore `outputs/` or the SQLite database when historical data is needed.
4. Restart the service.

```bash
sudo systemctl restart telegram-card-platform
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore.ps1 -BackupDir .\backups\telegram-card-platform-YYYYMMDD-HHMMSS
```

## Rollback To v120

See:

```text
feature_backups/v120_stable/ROLLBACK.md
```
