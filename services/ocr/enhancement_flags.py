from __future__ import annotations

from dataclasses import dataclass
import os


def _enabled(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class LocalHybridFlags:
    """新增本地协同能力的开关集合，关闭总开关时保持旧 Remote 路径。"""

    enabled: bool
    worker_queue_v2: bool
    busy_offline_separation: bool
    cpu_preprocess: bool
    cpu_ocr: bool
    cpu_shadow_only: bool
    cpu_can_affect_result: bool
    roi_review_v2: bool
    confirmation_mode: str
    sample_rate: float

    @property
    def cpu_ocr_effective(self) -> bool:
        return self.enabled and self.cpu_ocr

    @property
    def cpu_can_trigger_review(self) -> bool:
        return (
            self.cpu_ocr_effective
            and not self.cpu_shadow_only
            and self.cpu_can_affect_result
            and self.confirmation_mode == "strict"
        )


def load_local_hybrid_flags() -> LocalHybridFlags:
    enabled = _enabled("LOCAL_HYBRID_ENHANCEMENT_ENABLED")
    try:
        sample_rate = min(1.0, max(0.0, float(os.getenv("LOCAL_CPU_OCR_SAMPLE_RATE", "1.0"))))
    except ValueError:
        sample_rate = 1.0
    return LocalHybridFlags(
        enabled=enabled,
        worker_queue_v2=enabled and _enabled("LOCAL_WORKER_QUEUE_V2_ENABLED"),
        busy_offline_separation=enabled and _enabled("REMOTE_BUSY_OFFLINE_SEPARATION_ENABLED"),
        cpu_preprocess=enabled and _enabled("LOCAL_CPU_PREPROCESS_ENABLED"),
        cpu_ocr=enabled and _enabled("LOCAL_CPU_OCR_ENABLED"),
        cpu_shadow_only=_enabled("LOCAL_CPU_OCR_SHADOW_ONLY", True),
        cpu_can_affect_result=_enabled("LOCAL_CPU_OCR_CAN_AFFECT_RESULT"),
        roi_review_v2=enabled and _enabled("LOCAL_ROI_REVIEW_V2_ENABLED"),
        confirmation_mode=os.getenv("LOCAL_CPU_OCR_CONFIRMATION_MODE", "strict").strip().lower(),
        sample_rate=sample_rate,
    )
