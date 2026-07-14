from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import cv2


PREPROCESS_VERSION = "roi-v1"


def write_roi_crop(image_path: str | Path, box: Any, *, scale: int = 3) -> str | None:
    """只根据 GPU 同图坐标裁剪单个文本 ROI，不跨行也不拼接。"""
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
