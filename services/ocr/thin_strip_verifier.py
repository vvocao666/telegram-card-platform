from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract


PUBG_CARD_RE = re.compile(r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}")
THIN_STRIP_MAX_HEIGHT = 180
THIN_STRIP_MIN_ASPECT_RATIO = 2.0
OCR_TARGET_WIDTH = 1600
OCR_CONFIGS = (
    "--oem 3 --psm 6 --dpi 300 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-",
    "--oem 3 --psm 7 --dpi 300 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-",
)


def verify_thin_strip_pubg(
    image_path: Path,
    *,
    reader: Callable[[Image.Image, str], str] | None = None,
) -> tuple[str, ...]:
    """细长图仅在两次版面识别完全一致时返回复核候选。"""
    try:
        with Image.open(image_path) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
    except (OSError, ValueError):
        return tuple()
    if not is_thin_strip_size(*source.size):
        return tuple()

    prepared = prepare_thin_strip(source)
    read_text = reader or _read_with_tesseract
    candidates: list[str] = []
    for config in OCR_CONFIGS:
        try:
            cards = extract_pubg_cards(read_text(prepared, config))
        except Exception:
            return tuple()
        if len(cards) != 1:
            return tuple()
        candidates.append(cards[0])
    if len(set(candidates)) != 1:
        return tuple()
    return (candidates[0],)


def choose_thin_strip_consensus(
    cloud_cards: list[str] | tuple[str, ...],
    verified_cards: list[str] | tuple[str, ...],
    *,
    maximum_differences: int = 2,
) -> tuple[tuple[str, ...], bool]:
    """只从已识别出的完整候选中选择，不拼字也不生成新卡。"""
    if len(cloud_cards) != 1 or len(verified_cards) != 1:
        return tuple(cloud_cards), False
    cloud = cloud_cards[0]
    verified = verified_cards[0]
    if cloud == verified:
        return (cloud,), False
    if cloud[:6] != verified[:6]:
        return (cloud,), False
    cloud_compact = cloud.replace("-", "")
    verified_compact = verified.replace("-", "")
    if len(cloud_compact) != len(verified_compact):
        return (cloud,), False
    differences = sum(left != right for left, right in zip(cloud_compact, verified_compact))
    if differences > maximum_differences:
        return (cloud,), False
    return (verified,), True


def is_thin_strip_size(width: int, height: int) -> bool:
    return width > 0 and height > 0 and height <= THIN_STRIP_MAX_HEIGHT and width / height >= THIN_STRIP_MIN_ASPECT_RATIO


def prepare_thin_strip(source: Image.Image) -> Image.Image:
    width, height = source.size
    if width < OCR_TARGET_WIDTH:
        scale = OCR_TARGET_WIDTH / width
        source = source.resize((OCR_TARGET_WIDTH, max(1, int(height * scale))), Image.Resampling.LANCZOS)
    width, height = source.size
    # 保留卡密主体并去掉细长截图边缘噪声，比例沿用现有稳定本地 OCR 路径。
    cropped = source.crop((int(width * 0.03), int(height * 0.18), int(width * 0.97), int(height * 0.90)))
    gray = ImageOps.grayscale(cropped)
    contrast = ImageEnhance.Contrast(gray).enhance(1.9)
    sharpened = contrast.filter(ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3))
    return sharpened.point(lambda pixel: 255 if pixel > 178 else 0)


def extract_pubg_cards(text: str) -> list[str]:
    normalized = str(text).upper().replace(" ", "")
    return list(dict.fromkeys(PUBG_CARD_RE.findall(normalized)))


def _read_with_tesseract(image: Image.Image, config: str) -> str:
    return pytesseract.image_to_string(image, lang="eng", config=config)
