from PIL import Image, ImageDraw

from services.ocr.image_preprocess import crop_card_roi, preprocess_image


def test_pillow_preprocess_outputs_multiple_versions(tmp_path):
    image_path = tmp_path / "card.png"
    image = Image.new("RGB", (300, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 35), "S07304-F2V7-SGH8-NL72X", fill="black")
    image.save(image_path)

    variants = preprocess_image(image_path, output_dir=tmp_path / "preprocess")
    names = {variant.name for variant in variants}

    assert {"original", "gray", "binary", "upscaled", "roi"} <= names
    assert all(variant.path and variant.path.exists() for variant in variants)


def test_roi_failure_falls_back_to_original_image():
    image = Image.new("RGB", (120, 80), "white")

    roi, failed = crop_card_roi(image)

    assert failed
    assert roi.size == image.size
