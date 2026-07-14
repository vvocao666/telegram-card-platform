#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/telegram-card-platform}"
ENV_FILE="$APP_DIR/.env"
python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
keys = {
    "LOCAL_HYBRID_ENHANCEMENT_ENABLED": "true",
    "LOCAL_WORKER_QUEUE_V2_ENABLED": "true",
    "REMOTE_BUSY_OFFLINE_SEPARATION_ENABLED": "true",
    "LOCAL_CPU_PREPROCESS_ENABLED": "true",
    "LOCAL_CPU_OCR_ENABLED": "true",
    "LOCAL_CPU_OCR_SHADOW_ONLY": "false",
    "LOCAL_CPU_OCR_CAN_AFFECT_RESULT": "true",
    "LOCAL_ROI_REVIEW_V2_ENABLED": "true",
    "LOCAL_CPU_OCR_CONFIRMATION_MODE": "strict",
}
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0].strip()
    if key in keys:
        out.append(f"{key}={keys[key]}")
        seen.add(key)
    else:
        out.append(line)
out.extend(f"{key}={value}" for key, value in keys.items() if key not in seen)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
systemctl restart telegram-card-platform
