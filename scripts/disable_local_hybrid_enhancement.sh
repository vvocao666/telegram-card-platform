#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/telegram-card-platform}"
ENV_FILE="$APP_DIR/.env"
python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
out = ["LOCAL_HYBRID_ENHANCEMENT_ENABLED=false" if line.split("=", 1)[0].strip() == "LOCAL_HYBRID_ENHANCEMENT_ENABLED" else line for line in lines]
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
systemctl restart telegram-card-platform
