#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/s07-bot}"
REPO_URL="${REPO_URL:-https://github.com/vvocao666/pubg-psn-.git}"
SERVICE_NAME="${SERVICE_NAME:-s07-bot}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root." >&2
  exit 1
fi

apt-get update
apt-get install -y git python3 python3-venv python3-pip tesseract-ocr

if [ ! -d "$APP_DIR/.git" ]; then
  rm -rf "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python3" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python3" -m pip install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "Created $APP_DIR/.env. Fill BOT_TOKEN and OCR_SPACE_API_KEY before starting." >&2
  exit 2
fi

cp "$APP_DIR/systemd/s07-bot.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
"$APP_DIR/.venv/bin/python3" -m py_compile "$APP_DIR/bot.py"
systemctl restart "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME"
