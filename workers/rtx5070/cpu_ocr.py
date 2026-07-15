from __future__ import annotations

import os
import re
import threading
import time
import logging
from dataclasses import asdict
from typing import Any

from cpu_preprocess import PREPROCESS_VERSION, write_roi_crop
from model_registry import CpuModelStatus, validate_cpu_model


# PUBG is structurally strict: S07 + three digits + 4-4-5 groups.
# CPU shadow evidence must use the same acceptance boundary as the GPU path.
# The PSN branch explicitly rejects the three trailing PUBG groups of an
# incomplete PUBG token, so CPU evidence cannot invent a PSN conflict there.
CARD_RE = re.compile(
    r"(?<![A-Z0-9])(?:"
    r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}"
    r"|(?<!S07[0-9]{3}-)[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}"
    r")(?![A-Z0-9])"
)
PUBG_PREFIX_RE = re.compile(r"(?<![A-Z0-9])(?:S|5)0[0-9]{4}(?![0-9])")
LOGGER = logging.getLogger("rtx5070_worker.cpu_ocr")


class CpuOcrEngine:
    """CPU 仅给 GPU 输出提供同 ROI 的第二份证据，绝不补字或改字。"""

    def __init__(self, config: Any, metrics: Any) -> None:
        self._config = config
        self._metrics = metrics
        self._status: CpuModelStatus | None = None
        self._ocr = None
        self._last_error = ""
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(max(1, config.cpu_ocr_workers))

    def status(self) -> dict[str, Any]:
        status = self._model_status()
        return {
            "enabled": bool(self._config.cpu_ocr_effective),
            "available": bool(status.available and self._config.cpu_ocr_effective),
            "shadow_only": bool(self._config.cpu_shadow_only),
            "can_affect_result": bool(self._config.cpu_can_affect_result),
            "confirmation_mode": self._config.confirmation_mode,
            "model_version": status.version,
            "model_fingerprint": status.model_fingerprint,
            "preprocess_version": PREPROCESS_VERSION,
            "error": status.error,
            "last_error": self._last_error,
        }

    def inspect_gpu_lines(self, image_path: str, texts: list[dict[str, Any]]) -> dict[str, Any]:
        payload = self.status()
        payload.update({"latency_ms": 0, "lines": [], "conflicts": [], "roi_conflicts_resolved": False})
        if not payload["available"]:
            return payload
        started = time.monotonic()
        for item in texts:
            gpu_text = str(item.get("text", "")).upper()
            if not _is_cpu_roi_candidate(gpu_text) or not item.get("box"):
                continue
            evidence = self._inspect_line(image_path, item)
            if evidence is None:
                continue
            payload["lines"].append(evidence)
            gpu_cards = set(CARD_RE.findall(gpu_text))
            cpu_cards = set(CARD_RE.findall(evidence["raw_text"]))
            if gpu_cards != cpu_cards:
                payload["conflicts"].append({"box": evidence["box"], "gpu": sorted(gpu_cards), "cpu": sorted(cpu_cards)})
        payload["latency_ms"] = int((time.monotonic() - started) * 1000)
        if payload["conflicts"]:
            self._metrics.increment("cpu_conflicts")
        return payload

    def _inspect_line(self, image_path: str, item: dict[str, Any]) -> dict[str, Any] | None:
        started = time.monotonic()
        crop_path = write_roi_crop(image_path, item["box"])
        self._metrics.observe("cpu_preprocess", int((time.monotonic() - started) * 1000))
        if not crop_path:
            return None
        try:
            raw_text, score = self._recognize(crop_path)
        finally:
            try:
                os.unlink(crop_path)
            except OSError:
                pass
        return {"box": item["box"], "raw_text": raw_text, "score": score}

    def _recognize(self, image_path: str) -> tuple[str, float]:
        if not self._semaphore.acquire(timeout=2.0):
            return "", 0.0
        started = time.monotonic()
        try:
            ocr = self._get_ocr()
            if ocr is None:
                return "", 0.0
            result, _ = ocr(image_path, use_det=False, use_cls=False, use_rec=True)
            if not result:
                return "", 0.0
            lines, scores = _recognition_lines(result)
            text = "".join(lines).upper().replace(" ", "")
            return text, (sum(scores) / len(scores) if scores else 0.0)
        except Exception as exc:
            self._last_error = type(exc).__name__
            self._metrics.increment("cpu_ocr_failures")
            LOGGER.warning("CPU OCR ROI failed reason=%s", self._last_error)
            return "", 0.0
        finally:
            self._semaphore.release()
            self._metrics.observe("cpu_ocr", int((time.monotonic() - started) * 1000))

    def _model_status(self) -> CpuModelStatus:
        if self._status is None:
            self._status = validate_cpu_model()
        return self._status

    def _get_ocr(self):
        if not self._model_status().available:
            return None
        with self._lock:
            if self._ocr is None:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
            return self._ocr


def _is_cpu_roi_candidate(text: str) -> bool:
    """仅对 GPU 已定位的 PUBG 行做同 ROI 影子识别，保留 S 首位误读为 5 的证据。"""
    return bool(CARD_RE.search(text) or PUBG_PREFIX_RE.search(text))


def _recognition_lines(result: Any) -> tuple[list[str], list[float]]:
    """兼容 RapidOCR 的行级和带坐标两种返回结构，绝不把置信度当作文本。"""
    lines: list[str] = []
    scores: list[float] = []
    for row in result or ():
        if not isinstance(row, (list, tuple)):
            continue
        if len(row) >= 3 and isinstance(row[1], str):
            text, score = row[1], row[2]
        elif len(row) >= 2 and isinstance(row[0], str):
            text, score = row[0], row[1]
        else:
            continue
        lines.append(text)
        try:
            scores.append(float(score))
        except (TypeError, ValueError):
            pass
    return lines, scores
