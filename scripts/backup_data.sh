#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/s07-bot}"
OUTPUT_DIR="${OUTPUT_DIR:-$APP_DIR/outputs}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups/data}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

timestamp="$(date +%Y%m%d-%H%M%S)"
archive="$BACKUP_DIR/s07-data-$timestamp.tar.gz"

if [ ! -d "$OUTPUT_DIR" ]; then
  echo "outputs directory does not exist: $OUTPUT_DIR"
  exit 0
fi

tar \
  --exclude='*.tmp' \
  --exclude='*.jpg' \
  --exclude='*.jpeg' \
  --exclude='*.png' \
  -czf "$archive" \
  -C "$APP_DIR" outputs

find "$BACKUP_DIR" -type f -name 's07-data-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "$archive"
