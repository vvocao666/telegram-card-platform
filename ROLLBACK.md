# Rollback Guide

## Recommended Cloud Stable

The recommended general cloud-server stable release is:

```text
v1.3.0-ocr-learning-plus
```

This is the last general stable version before owner-specific Hybrid OCR features were added.

Use this version when the server does not have:

- Windows RTX5070 OCR Worker
- Tailscale
- `REMOTE_OCR_URL`
- Hybrid OCR routing
- Local GPU-first OCR

Do not treat `strict-v120-owner-broadcast-no-trx` or the v120 backup as the newest stable release. v120 is only a historical pre-modular rollback point.

## Roll Back To v1.3.0

```bash
cd /opt/telegram-card-platform
sudo systemctl stop telegram-card-platform
git fetch --tags
git checkout v1.3.0-ocr-learning-plus
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m compileall -q bot.py config handlers services storage utils tests
sudo systemctl start telegram-card-platform
sudo systemctl status telegram-card-platform --no-pager
```

Keep the existing production `.env`, `outputs/`, and `ledger.sqlite3` unless you intentionally restore them from a backup.

## Owner Hybrid OCR Line

The `v2.x` releases are for the owner production environment with:

- Windows RTX5070 OCR Worker
- Tailscale
- `REMOTE_OCR_URL`
- Hybrid OCR
- Local GPU-first OCR

Do not use `v2.x` as the default cloud-only deployment target.
