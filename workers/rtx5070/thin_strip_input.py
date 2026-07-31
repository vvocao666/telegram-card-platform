from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import cv2
    import numpy as np
except Exception:  # Cloud-only installs do not include Worker image dependencies.
    cv2 = None
    np = None


@dataclass(frozen=True)
class PreparedWorkerInput:
    data: bytes
    suffix: str
    padding_applied: bool = False
    offset_x: int = 0
    offset_y: int = 0


def prepare_worker_input(
    image_bytes: bytes,
    suffix: str,
    metrics: dict[str, Any],
) -> PreparedWorkerInput:
    """Add a small background border when text can touch an image edge.

    The border gives the detector room around glyphs touching an image edge. It
    does not crop, resize, rewrite, or infer any card character.
    """
    width = int(metrics.get("width", 0) or 0)
    height = int(metrics.get("height", 0) or 0)
    extreme_thin_strip = height <= 120 and width / max(height, 1) >= 3.0
    narrow_vertical_list = width <= 480 and height >= 180 and height / max(width, 1) >= 1.2
    if (
        cv2 is None
        or np is None
        or width <= 0
        or height <= 0
        or not (extreme_thin_strip or narrow_vertical_list)
    ):
        return PreparedWorkerInput(image_bytes, suffix)

    try:
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return PreparedWorkerInput(image_bytes, suffix)

        border_x = max(12, min(48, round(width * 0.04)))
        border_y = max(6, min(20, round(height * 0.15)))
        edge_pixels = np.concatenate(
            (
                image[0, :, :],
                image[-1, :, :],
                image[:, 0, :],
                image[:, -1, :],
            ),
            axis=0,
        )
        sampled_background = tuple(int(value) for value in np.median(edge_pixels, axis=0))
        brightness = sum(sampled_background) / len(sampled_background)
        if brightness >= 180:
            background = (255, 255, 255)
        elif brightness <= 75:
            background = (0, 0, 0)
        else:
            background = sampled_background
        padded = cv2.copyMakeBorder(
            image,
            border_y,
            border_y,
            border_x,
            border_x,
            cv2.BORDER_CONSTANT,
            value=background,
        )
        success, encoded = cv2.imencode(".png", padded)
        if not success:
            return PreparedWorkerInput(image_bytes, suffix)
        return PreparedWorkerInput(
            encoded.tobytes(),
            ".png",
            padding_applied=True,
            offset_x=border_x,
            offset_y=border_y,
        )
    except Exception:
        return PreparedWorkerInput(image_bytes, suffix)
