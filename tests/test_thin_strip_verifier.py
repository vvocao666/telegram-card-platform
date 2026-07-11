from PIL import Image

from services.ocr.thin_strip_verifier import (
    choose_thin_strip_consensus,
    is_thin_strip_size,
    verify_thin_strip_pubg,
)


CORRECT = "S07336-Z5QW-USKA-W2HQY"
CLOUD_WRONG = "S07336-25QW-USKA-W2HQY"


def test_detects_only_low_height_wide_images_as_thin_strips():
    assert is_thin_strip_size(313, 82)
    assert not is_thin_strip_size(313, 300)
    assert not is_thin_strip_size(1080, 1920)


def test_verifier_requires_two_identical_complete_results(tmp_path):
    path = tmp_path / "thin.png"
    Image.new("RGB", (313, 82), "white").save(path)
    responses = iter((CORRECT, CORRECT))
    assert verify_thin_strip_pubg(path, reader=lambda _image, _config: next(responses)) == (CORRECT,)


def test_verifier_rejects_disagreement_or_incomplete_result(tmp_path):
    path = tmp_path / "thin.png"
    Image.new("RGB", (313, 82), "white").save(path)
    responses = iter((CORRECT, CLOUD_WRONG))
    assert verify_thin_strip_pubg(path, reader=lambda _image, _config: next(responses)) == tuple()
    incomplete = iter(("S07336-Z5QW-USKA-W2HQ", "S07336-Z5QW-USKA-W2HQ"))
    assert verify_thin_strip_pubg(path, reader=lambda _image, _config: next(incomplete)) == tuple()


def test_verifier_safely_skips_when_tesseract_is_unavailable(tmp_path):
    path = tmp_path / "thin.png"
    Image.new("RGB", (313, 82), "white").save(path)

    def unavailable(_image, _config):
        raise RuntimeError("tesseract unavailable")

    assert verify_thin_strip_pubg(path, reader=unavailable) == tuple()


def test_consensus_selects_observed_verified_card_with_two_differences_or_less():
    selected, used = choose_thin_strip_consensus([CLOUD_WRONG], [CORRECT])
    assert selected == (CORRECT,)
    assert used is True


def test_consensus_does_not_guess_when_candidates_are_too_different():
    cloud = "S07336-AAAA-BBBB-CCCCC"
    verified = "S07336-Z5QW-USKA-W2HQY"
    selected, used = choose_thin_strip_consensus([cloud], [verified])
    assert selected == (cloud,)
    assert used is False
