from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


def process_memory_mb() -> str:
    try:
        if os.name == "posix":
            statm = Path("/proc/self/statm")
            if statm.exists():
                pages = int(statm.read_text(encoding="utf-8").split()[1])
                return f"{pages * os.sysconf('SC_PAGE_SIZE') / 1024 / 1024:.1f} MB"
    except Exception:
        pass
    return "unknown"


def process_uptime_text(started_at: float) -> str:
    seconds = max(0, int(time.time() - started_at))
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"


def git_output(args: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or Path("."),
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
    except Exception:
        return "unknown"
    value = (result.stdout or "").strip()
    return value or "unknown"


def service_active_state(service_name: str = "telegram-card-platform") -> str:
    if os.name != "posix":
        return "unknown"
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
    except Exception:
        return "unknown"
    return (result.stdout or "").strip() or "unknown"
