#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/telegram-card-platform}"
REF="${REF:-main}"
BACKUP_ROOT="${BACKUP_ROOT:-/root/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/before_cloud_deploy_$TIMESTAMP"

mkdir -p "$BACKUP_DIR"

if [ -d "$APP_DIR" ]; then
  cp -a "$APP_DIR" "$BACKUP_DIR/project"
fi

if [ -f /etc/systemd/system/telegram-card-platform.service ]; then
  cp -a /etc/systemd/system/telegram-card-platform.service "$BACKUP_DIR/telegram-card-platform.service"
fi

systemctl stop telegram-card-platform || true

cd "$APP_DIR"
git fetch --tags origin "$REF"
git checkout "$REF"
git pull --ff-only origin "$REF"

if [ ! -f .env ]; then
  cp .env.example .env
fi

.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m compileall -q bot.py config handlers services storage utils tests
.venv/bin/python3 -m pytest -q

systemctl daemon-reload
systemctl start telegram-card-platform
systemctl status telegram-card-platform --no-pager

echo "备份目录：$BACKUP_DIR"
