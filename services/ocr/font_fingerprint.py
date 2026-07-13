from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path

from PIL import Image, ImageOps

from services.ocr.image_pixels import flattened_pixels


@dataclass(frozen=True)
class FontFingerprint:
    font_hash: str
    card_type: str | None
    character_height: int
    character_width: int
    line_spacing: int
    stroke_thickness: int
    grayscale_bucket: int
    black_text_ratio: float
    crop_ratio: float


def build_font_fingerprint(
    image: Image.Image | Path | str,
    card_type: str | None = None,
    crop_box: tuple[int, int, int, int] | None = None,
) -> FontFingerprint:
    source = _load_image(image)
    original_area = max(source.width * source.height, 1)
    if crop_box:
        source = source.crop(crop_box)
    gray = ImageOps.grayscale(source)
    pixels = flattened_pixels(gray)
    threshold = _otsu_like_threshold(pixels)
    dark_pixels = [(index % gray.width, index // gray.width) for index, value in enumerate(pixels) if value < threshold]
    bbox = _dark_bbox(dark_pixels, gray.size)
    character_height = _estimate_character_height(dark_pixels, bbox)
    character_width = _estimate_character_width(dark_pixels, bbox)
    line_spacing = _estimate_line_spacing(dark_pixels, gray.height)
    stroke_thickness = _estimate_stroke_thickness(dark_pixels)
    grayscale_bucket = int(sum(pixels) / max(len(pixels), 1) // 16)
    black_text_ratio = round(len(dark_pixels) / max(len(pixels), 1), 4)
    crop_ratio = round((gray.width * gray.height) / original_area, 4)
    digest = _fingerprint_digest(
        card_type,
        character_height,
        character_width,
        line_spacing,
        stroke_thickness,
        grayscale_bucket,
        black_text_ratio,
        crop_ratio,
    )
    prefix = (card_type or "ocr").lower()
    return FontFingerprint(
        font_hash=f"{prefix}_font_a_{digest}",
        card_type=card_type,
        character_height=character_height,
        character_width=character_width,
        line_spacing=line_spacing,
        stroke_thickness=stroke_thickness,
        grayscale_bucket=grayscale_bucket,
        black_text_ratio=black_text_ratio,
        crop_ratio=crop_ratio,
    )


def fingerprint_to_dict(fingerprint: FontFingerprint) -> dict[str, object]:
    return asdict(fingerprint)


def _load_image(image: Image.Image | Path | str) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    with Image.open(image) as opened:
        return opened.convert("RGB")


def _otsu_like_threshold(pixels: list[int]) -> int:
    if not pixels:
        return 180
    values = sorted(pixels)
    lower = values[len(values) // 3]
    upper = values[(len(values) * 2) // 3]
    return max(80, min(220, (lower + upper) // 2))


def _dark_bbox(dark_pixels: list[tuple[int, int]], size: tuple[int, int]) -> tuple[int, int, int, int]:
    if not dark_pixels:
        return (0, 0, size[0], size[1])
    xs = [x for x, _ in dark_pixels]
    ys = [y for _, y in dark_pixels]
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def _estimate_character_height(dark_pixels: list[tuple[int, int]], bbox: tuple[int, int, int, int]) -> int:
    if not dark_pixels:
        return 0
    rows = sorted({y for _, y in dark_pixels})
    runs = _runs(rows)
    if not runs:
        return bbox[3] - bbox[1]
    return int(sum(end - start + 1 for start, end in runs) / len(runs))


def _estimate_character_width(dark_pixels: list[tuple[int, int]], bbox: tuple[int, int, int, int]) -> int:
    if not dark_pixels:
        return 0
    columns = sorted({x for x, _ in dark_pixels})
    runs = [run for run in _runs(columns) if run[1] - run[0] + 1 >= 2]
    if not runs:
        return bbox[2] - bbox[0]
    return int(sum(end - start + 1 for start, end in runs) / len(runs))


def _estimate_line_spacing(dark_pixels: list[tuple[int, int]], height: int) -> int:
    if not dark_pixels:
        return height
    rows = sorted({y for _, y in dark_pixels})
    runs = _runs(rows)
    gaps = [runs[index + 1][0] - runs[index][1] - 1 for index in range(len(runs) - 1)]
    gaps = [gap for gap in gaps if gap > 0]
    if not gaps:
        return 0
    return int(sum(gaps) / len(gaps))


def _estimate_stroke_thickness(dark_pixels: list[tuple[int, int]]) -> int:
    if not dark_pixels:
        return 0
    by_row: dict[int, list[int]] = {}
    for x, y in dark_pixels:
        by_row.setdefault(y, []).append(x)
    runs = []
    for xs in by_row.values():
        runs.extend(end - start + 1 for start, end in _runs(sorted(xs)))
    runs = [run for run in runs if run <= 8]
    if not runs:
        return 1
    return max(1, int(sum(runs) / len(runs)))


def _runs(values: list[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    runs: list[tuple[int, int]] = []
    start = values[0]
    previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        runs.append((start, previous))
        start = previous = value
    runs.append((start, previous))
    return runs


def _fingerprint_digest(*values: object) -> str:
    raw = "|".join(str(value) for value in values)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
