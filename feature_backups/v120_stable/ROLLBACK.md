# Rollback to v120 Stable

Baseline version: `strict-v120-owner-broadcast-no-trx`

This folder stores the last confirmed stable online version before the final modular refactor.

## Restore Files

From the project root, run:

```powershell
Copy-Item feature_backups/v120_stable/bot.py . -Force
Copy-Item feature_backups/v120_stable/ledger_commands.py . -Force
Copy-Item feature_backups/v120_stable/ledger_storage.py . -Force
Copy-Item feature_backups/v120_stable/.env.example . -Force
Copy-Item feature_backups/v120_stable/requirements.txt . -Force
```

## Verify

```powershell
python -m pytest
python -m py_compile bot.py ledger_commands.py ledger_storage.py
```

## Restart Service

Linux systemd:

```bash
sudo systemctl restart telegram-card-platform
sudo systemctl is-active telegram-card-platform
```

Windows local run should use the same `.env` and virtual environment as before.
