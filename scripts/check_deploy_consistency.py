"""检查 Cloud Deploy 与 Owner Hybrid 是否仍共享同一业务代码源。"""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_PATHS = ("bot.py", "config", "handlers", "services", "storage", "utils")


def digest_business_source() -> str:
    """按路径和内容生成业务源码摘要，不包含部署模板与运行数据。"""
    hasher = hashlib.sha256()
    for relative in BUSINESS_PATHS:
        path = ROOT / relative
        paths = [path] if path.is_file() else sorted(item for item in path.rglob("*.py") if item.is_file())
        for item in paths:
            hasher.update(item.relative_to(ROOT).as_posix().encode("utf-8"))
            # Windows and Linux checkouts may differ only by CRLF/LF. Normalize
            # line endings so this release check compares source, not checkout format.
            hasher.update(item.read_bytes().replace(b"\r\n", b"\n"))
    return hasher.hexdigest()


def main() -> int:
    cloud = ROOT / "deploy" / "cloud"
    hybrid = ROOT / "deploy" / "owner-hybrid"
    for required in (cloud / "install.sh", cloud / "update.sh", hybrid / "install.sh"):
        if not required.is_file():
            raise SystemExit(f"missing deployment entry: {required.relative_to(ROOT)}")

    cloud_env = (ROOT / ".env.cloud.example").read_text(encoding="utf-8")
    hybrid_env = (ROOT / ".env.owner-hybrid.example").read_text(encoding="utf-8")
    if "REMOTE_OCR_ENABLED=false" not in cloud_env:
        raise SystemExit("Cloud Deploy must keep Remote OCR disabled by default")
    if "REMOTE_OCR_ENABLED=true" not in hybrid_env:
        raise SystemExit("Owner Hybrid must document Remote OCR as an opt-in")

    print(f"business_source_sha256={digest_business_source()}")
    print("deployment_modes=shared_source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
