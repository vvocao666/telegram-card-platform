from __future__ import annotations

from PIL import Image


def flattened_pixels(image: Image.Image) -> list[int]:
    getter = getattr(image, "get_flattened_data", None)
    if callable(getter):
        return list(getter())
    return list(image.getdata())
