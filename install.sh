#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/telegram-card-platform}"
REPO_URL="${REPO_URL:-https://github.com/vvocao666/telegram-card-platform.git}"
REF="${REF:-main}"

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git fetch --tags origin "$REF"
git checkout "$REF"
git pull --ff-only origin "$REF"

apt-get update
apt-get install -y python3 python3-venv python3-pip git tesseract-ocr

python3 -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i 's/^REMOTE_OCR_ENABLED=.*/REMOTE_OCR_ENABLED=false/' .env
fi

mkdir -p /etc/telegram-card-platform
printf 'APP_DIR=%s\nPYTHON_BIN=.venv/bin/python3\n' "$APP_DIR" > /etc/telegram-card-platform/service.env
cp systemd/telegram-card-platform.service /etc/systemd/system/telegram-card-platform.service

systemctl daemon-reload
systemctl enable telegram-card-platform

echo "安装完成。请编辑 $APP_DIR/.env 后执行："
echo "systemctl start telegram-card-platform"
echo "systemctl status telegram-card-platform --no-pager"
