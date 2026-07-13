from PIL import Image

from services.ocr.image_pixels import flattened_pixels


def test_flattened_pixels_preserves_pixel_order():
    image = Image.new("L", (2, 2))
    image.putdata([1, 2, 3, 4])

    assert flattened_pixels(image) == [1, 2, 3, 4]
