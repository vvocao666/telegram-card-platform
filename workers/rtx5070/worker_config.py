from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def load_worker_env(path: Path | None = None) -> None:
    """仅加载 Worker 自己的新开关文件，不触碰机器人或现有环境变量。"""
    target = path or Path(__file__).resolve().parent / "hybrid.env"
    if not target.is_file():
        return
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # hybrid.env 是 Worker 专属部署开关，必须覆盖 Windows 服务遗留的同名环境变量。
        # 仅解析该文件中的键，不触碰机器人或系统其它配置。
        os.environ[key.strip()] = value.strip()


def _enabled(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return min(maximum, max(minimum, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


@dataclass(frozen=True)
class WorkerHybridConfig:
    enabled: bool
    queue_v2_enabled: bool
    cpu_preprocess_enabled: bool
    cpu_ocr_enabled: bool
    cpu_shadow_only: bool
    cpu_can_affect_result: bool
    roi_review_v2_enabled: bool
    confirmation_mode: str
    cpu_preprocess_workers: int
    cpu_ocr_workers: int
    queue_workers: int
    queue_capacity: int

    @property
    def cpu_ocr_effective(self) -> bool:
        return self.enabled and self.cpu_ocr_enabled


def load_worker_config() -> WorkerHybridConfig:
    enabled = _enabled("LOCAL_HYBRID_ENHANCEMENT_ENABLED")
    return WorkerHybridConfig(
        enabled=enabled,
        queue_v2_enabled=enabled and _enabled("LOCAL_WORKER_QUEUE_V2_ENABLED"),
        cpu_preprocess_enabled=enabled and _enabled("LOCAL_CPU_PREPROCESS_ENABLED"),
        cpu_ocr_enabled=enabled and _enabled("LOCAL_CPU_OCR_ENABLED"),
        cpu_shadow_only=_enabled("LOCAL_CPU_OCR_SHADOW_ONLY", True),
        cpu_can_affect_result=_enabled("LOCAL_CPU_OCR_CAN_AFFECT_RESULT"),
        roi_review_v2_enabled=enabled and _enabled("LOCAL_ROI_REVIEW_V2_ENABLED"),
        confirmation_mode=os.getenv("LOCAL_CPU_OCR_CONFIRMATION_MODE", "strict").strip().lower(),
        cpu_preprocess_workers=_integer("LOCAL_CPU_PREPROCESS_WORKERS", 4, 1, 12),
        cpu_ocr_workers=_integer("LOCAL_CPU_OCR_WORKERS", 2, 1, 6),
        queue_workers=_integer("LOCAL_WORKER_QUEUE_WORKERS", 4, 1, 8),
        queue_capacity=_integer("LOCAL_WORKER_QUEUE_CAPACITY", 32, 2, 128),
    )
