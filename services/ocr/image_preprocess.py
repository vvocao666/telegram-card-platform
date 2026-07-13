from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from services.ocr.image_pixels import flattened_pixels


DEFAULT_PREPROCESS_DIR = Path("outputs/preprocess")
MAX_SIDE = 3000


@dataclass(frozen=True)
class PreprocessVariant:
    name: str
    image: Image.Image
    path: Path | None = None
    quality_score: float = 0.0
    roi_failed: bool = False


def preprocess_image(
    image_path: Path | str,
    output_dir: Path | str = DEFAULT_PREPROCESS_DIR,
    save_debug: bool = True,
) -> list[PreprocessVariant]:
    try:
        with Image.open(image_path) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
        source = _limit_size(source)
        variants = _build_variants(source)
        if save_debug:
            variants = [_save_variant(variant, Path(output_dir), Path(image_path).stem) for variant in variants]
        return variants
    except Exception:
        with Image.open(image_path) as opened:
            fallback = ImageOps.exif_transpose(opened).convert("RGB")
        return [PreprocessVariant("original", fallback, quality_score=image_quality_score(fallback), roi_failed=True)]


def _build_variants(source: Image.Image) -> list[PreprocessVariant]:
    gray = ImageOps.grayscale(source)
    denoised = gray.filter(ImageFilter.MedianFilter(size=3))
    sharpened = ImageEnhance.Sharpness(denoised).enhance(1.8)
    binary = sharpened.point(lambda pixel: 255 if pixel > 170 else 0)
    upscaled = sharpened.resize((sharpened.width * 2, sharpened.height * 2), Image.Resampling.LANCZOS)
    roi, roi_failed = crop_card_roi(sharpened)
    return [
        PreprocessVariant("original", source, quality_score=image_quality_score(source)),
        PreprocessVariant("gray", gray.convert("RGB"), quality_score=image_quality_score(gray)),
        PreprocessVariant("binary", binary.convert("RGB"), quality_score=image_quality_score(binary)),
        PreprocessVariant("upscaled", upscaled.convert("RGB"), quality_score=image_quality_score(upscaled)),
        PreprocessVariant("roi", roi.convert("RGB"), quality_score=image_quality_score(roi), roi_failed=roi_failed),
    ]


def crop_card_roi(image: Image.Image) -> tuple[Image.Image, bool]:
    gray = ImageOps.grayscale(image)
    pixels = flattened_pixels(gray)
    threshold = max(60, min(210, int(sum(pixels) / max(len(pixels), 1)) - 20))
    dark = [(index % gray.width, index // gray.width) for index, value in enumerate(pixels) if value < threshold]
    if not dark:
        return image, True
    xs = [x for x, _ in dark]
    ys = [y for _, y in dark]
    left = max(min(xs) - 8, 0)
    top = max(min(ys) - 8, 0)
    right = min(max(xs) + 9, gray.width)
    bottom = min(max(ys) + 9, gray.height)
    if right - left < gray.width * 0.25 or bottom - top < gray.height * 0.08:
        return image, True
    return image.crop((left, top, right, bottom)), False


def image_quality_score(image: Image.Image) -> float:
    gray = ImageOps.grayscale(image)
    pixels = flattened_pixels(gray)
    if not pixels:
        return 0.0
    mean = sum(pixels) / len(pixels)
    variance = sum((pixel - mean) ** 2 for pixel in pixels) / len(pixels)
    contrast_score = min(50.0, (variance ** 0.5) / 2)
    dark_ratio = sum(1 for pixel in pixels if pixel < 120) / len(pixels)
    text_score = min(30.0, dark_ratio * 300)
    size_score = 20.0 if min(gray.size) >= 80 else 10.0
    return round(min(100.0, contrast_score + text_score + size_score), 2)


def _limit_size(image: Image.Image) -> Image.Image:
    max_side = max(image.size)
    if max_side <= MAX_SIDE:
        return image
    scale = MAX_SIDE / max_side
    return image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)


def _save_variant(variant: PreprocessVariant, output_dir: Path, stem: str) -> PreprocessVariant:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{stem}_{variant.name}.png"
    variant.image.save(path, format="PNG", optimize=True)
    return PreprocessVariant(
        name=variant.name,
        image=variant.image,
        path=path,
        quality_score=variant.quality_score,
        roi_failed=variant.roi_failed,
    )
