from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from thin_strip_input import prepare_worker_input


def _encoded_image(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    image = np.full((height, width, 3), color, dtype=np.uint8)
    success, encoded = cv2.imencode(".png", image)
    assert success
    return encoded.tobytes()


def test_extreme_thin_strip_gets_background_padding():
    source = _encoded_image(270, 33, (214, 220, 225))

    prepared = prepare_worker_input(
        source,
        ".png",
        {"width": 270, "height": 33, "image_variance": 10.0},
    )

    assert prepared.padding_applied is True
    assert (prepared.offset_x, prepared.offset_y) == (12, 6)
    decoded = cv2.imdecode(np.frombuffer(prepared.data, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (45, 294)
    assert np.all(decoded[6:39, 12:282] == (214, 220, 225))


def test_regular_image_is_unchanged():
    source = _encoded_image(500, 400, (255, 255, 255))

    prepared = prepare_worker_input(
        source,
        ".png",
        {"width": 500, "height": 400, "image_variance": 100.0},
    )

    assert prepared.padding_applied is False
    assert prepared.data is source
    assert prepared.suffix == ".png"
