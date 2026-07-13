from services.ocr.photo_rate_limiter import batch_capacity_reached


def test_zero_batch_limit_never_drops_images():
    assert batch_capacity_reached(0, 0) is False
    assert batch_capacity_reached(10_000, 0) is False


def test_explicit_batch_limit_is_still_supported():
    assert batch_capacity_reached(49, 50) is False
    assert batch_capacity_reached(50, 50) is True
