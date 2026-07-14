#!/usr/bin/env bash
set -euo pipefail

# Cloud Deploy uses the shared application source and keeps Remote OCR disabled.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export REF="${REF:-main}"
export APP_DIR="${APP_DIR:-/opt/telegram-card-platform}"
exec "$ROOT/install.sh" "$@"
