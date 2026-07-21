from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

try:
    import cv2
    import numpy as np
except Exception:  # Cloud Deploy test environments do not install Worker-only OpenCV.
    cv2 = None
    np = None


PREPROCESS_VERSION = "roi-v3"


def cpu_evidence_image_path(
    original_path: str,
    enhanced_path: str | None,
    best_engine: str,
) -> str:
    """CPU ROI 必须使用与 GPU 最终坐标相同的图像版本。"""
    if best_engine == "enhanced" and enhanced_path:
        return enhanced_path
    return original_path


def should_prepare_enhanced(metrics: dict[str, Any]) -> bool:
    """Only prebuild variants for images that necessarily leave the GPU fast path."""
    width = int(metrics.get("width", 0) or 0)
    height = int(metrics.get("height", 0) or 0)
    variance = float(metrics.get("image_variance", 0.0) or 0.0)
    return width < 350 or height > 500 or variance < 80.0


class CpuPreparationPool:
    """Prepare a possible enhancement while the serialized GPU handles the original."""

    def __init__(self, config: Any, metrics: Any) -> None:
        self._enabled = bool(getattr(config, "cpu_preprocess_enabled", False))
        self._metrics = metrics
        workers = max(1, int(getattr(config, "cpu_preprocess_workers", 1)))
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cpu-preprocess")

    def start(self, image_bytes: bytes, suffix: str, metrics: dict[str, Any]) -> Future[str | None] | None:
        if not self._enabled or not should_prepare_enhanced(metrics):
            return None
        return self._executor.submit(self._prepare, image_bytes, suffix)

    def result(self, future: Future[str | None] | None) -> str | None:
        if future is None:
            return None
        try:
            return future.result()
        except Exception:
            return None

    def _prepare(self, image_bytes: bytes, suffix: str) -> str | None:
        started = time.monotonic()
        try:
            return write_enhanced_image(image_bytes, suffix)
        finally:
            self._metrics.observe("cpu_preprocess", int((time.monotonic() - started) * 1000))


def write_enhanced_image(data: bytes, suffix: str) -> str | None:
    """Use the existing OpenCV enhancement exactly once; return None on failure."""
    if cv2 is None or np is None:
        return None
    try:
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        filtered = cv2.bilateralFilter(enhanced, 5, 50, 50)
        blurred = cv2.GaussianBlur(filtered, (0, 0), 1.0)
        sharpened = cv2.addWeighted(filtered, 1.6, blurred, -0.6, 0)
        upscaled = cv2.resize(sharpened, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
        output_suffix = suffix if suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp") else ".jpg"
        success, encoded = cv2.imencode(output_suffix, upscaled)
        if not success:
            return None
        handle, target = tempfile.mkstemp(suffix=output_suffix)
        with os.fdopen(handle, "wb") as output:
            output.write(encoded.tobytes())
        return target
    except Exception:
        return None
    return None


def write_roi_crop(image_path: str | Path, box: Any, *, scale: int = 3) -> str | None:
    """只根据 GPU 同图坐标裁剪单个文本 ROI，不跨行也不拼接。"""
    if cv2 is None:
        return None
    image = cv2.imread(str(image_path))
    if image is None:
        return None
    values = flatten_box(box)
    if len(values) < 4:
        return None
    x1, y1, x2, y2 = values[:4]
    height, width = image.shape[:2]
    margin_x = max(6, int((x2 - x1) * 0.08))
    margin_y = max(4, int((y2 - y1) * 0.30))
    x1, y1 = max(0, x1 - margin_x), max(0, y1 - margin_y)
    x2, y2 = min(width, x2 + margin_x), min(height, y2 + margin_y)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = image[y1:y2, x1:x2]
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    handle, target = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    if not cv2.imwrite(target, crop):
        os.unlink(target)
        return None
    return target


def flatten_box(box: Any) -> list[int]:
    values = box.tolist() if hasattr(box, "tolist") else box
    if not isinstance(values, (list, tuple)):
        return []
    if values and isinstance(values[0], (list, tuple)):
        xs = [int(point[0]) for point in values]
        ys = [int(point[1]) for point in values]
        return [min(xs), min(ys), max(xs), max(ys)]
    return [int(value) for value in values]
