from __future__ import annotations

from typing import Any


def cpu_payload_requires_review(payload: dict[str, Any]) -> bool:
    """CPU 只能触发复核，不能直接替换 GPU 卡密。"""
    cpu = payload.get("cpu_ocr")
    if not isinstance(cpu, dict):
        return False
    if not cpu.get("enabled") or cpu.get("shadow_only"):
        return False
    if not cpu.get("can_affect_result") or cpu.get("confirmation_mode") != "strict":
        return False
    return bool(cpu.get("conflicts")) and not bool(cpu.get("roi_conflicts_resolved"))


def cpu_payload_is_available(payload: dict[str, Any]) -> bool:
    cpu = payload.get("cpu_ocr")
    return isinstance(cpu, dict) and bool(cpu.get("available"))
