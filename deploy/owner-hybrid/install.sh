#!/usr/bin/env bash
set -euo pipefail

# This installs the same Cloud Deploy application source. Configure Remote OCR only in .env.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export REF="${REF:-main}"
export APP_DIR="${APP_DIR:-/opt/telegram-card-platform}"
exec "$ROOT/install.sh" "$@"
