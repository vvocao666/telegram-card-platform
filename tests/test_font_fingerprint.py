from PIL import Image, ImageDraw

from services.ocr.font_fingerprint import build_font_fingerprint


def test_font_fingerprint_is_stable_for_same_image():
    image = Image.new("RGB", (320, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.text((12, 20), "S07304-GM7D-JQ93-9NHLV", fill="black")

    first = build_font_fingerprint(image, card_type="PUBG")
    second = build_font_fingerprint(image, card_type="PUBG")

    assert first.font_hash == second.font_hash
    assert first.font_hash.startswith("pubg_font_a_")
    assert first.character_height >= 0
    assert first.character_width >= 0
    assert first.black_text_ratio > 0


def test_font_fingerprint_respects_crop_ratio():
    image = Image.new("RGB", (400, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 30), "PFP7-FP8X-26PH", fill="black")

    fingerprint = build_font_fingerprint(image, card_type="PSN", crop_box=(0, 0, 200, 60))

    assert fingerprint.font_hash.startswith("psn_font_a_")
    assert 0 < fingerprint.crop_ratio < 1
