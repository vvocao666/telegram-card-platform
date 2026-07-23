from __future__ import annotations

from pathlib import Path

import gpu_variant_review as review


CORRECT = "S07336-VLHL-MDZH-6S8ML"
ENHANCED_WRONG = "S07336-VLHL-MDZH-6S6ML"


def _result(card: str, score: float = 0.98, *, box=None) -> dict:
    texts = [{"text": card, "score": score, "box": box}] if box else []
    return {"cards": [{"text": card, "score": score}], "texts": texts}


def test_mild_review_can_restore_original_candidate_without_inventing_card(
    monkeypatch, tmp_path: Path
) -> None:
    image = tmp_path / "original.png"
    image.write_bytes(b"image")
    mild = tmp_path / "mild.png"
    mild.write_bytes(b"mild")
    monkeypatch.setattr(review, "write_mild_review_image", lambda _path: str(mild))

    result = review.review_gpu_variant_conflict(
        str(image),
        _result(CORRECT, 0.9471),
        _result(ENHANCED_WRONG, 0.9860),
        lambda _path: (_result(CORRECT, 0.9756), 112),
    )

    assert result.resolved is True
    assert result.selected_engine == "original"
    assert result.selected_card == CORRECT
    assert result.review_card == CORRECT
    assert result.reason == "mild_original_confirmation"


def test_roi_review_uses_original_card_box(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "original.png"
    image.write_bytes(b"image")
    roi = tmp_path / "roi.png"
    roi.write_bytes(b"roi")
    seen = {}

    def fake_roi(path, box, *, scale):
        seen.update(path=str(path), box=box, scale=scale)
        return str(roi)

    monkeypatch.setattr(review, "write_roi_crop", fake_roi)
    monkeypatch.setattr(
        review,
        "write_mild_review_image",
        lambda _path: (_ for _ in ()).throw(AssertionError("whole image must not be used")),
    )

    result = review.review_gpu_variant_conflict(
        str(image),
        _result(CORRECT, 0.9471, box=[10, 20, 310, 58]),
        _result(ENHANCED_WRONG, 0.9860),
        lambda path: (_result(CORRECT, 0.9756), 45)
        if path == str(roi)
        else (_result(""), 0),
    )

    assert result.resolved is True
    assert result.reason == "roi_original_confirmation"
    assert seen == {
        "path": str(image),
        "box": [10, 20, 310, 58],
        "scale": 3,
    }


def test_mild_review_rejects_a_third_candidate(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "original.png"
    image.write_bytes(b"image")
    mild = tmp_path / "mild.png"
    mild.write_bytes(b"mild")
    monkeypatch.setattr(review, "write_mild_review_image", lambda _path: str(mild))

    result = review.review_gpu_variant_conflict(
        str(image),
        _result(CORRECT),
        _result(ENHANCED_WRONG),
        lambda _path: (_result("S07336-VLHL-MDZH-6SBML"), 90),
    )

    assert result.resolved is False
    assert result.reason == "third_candidate"


def test_mild_review_does_not_run_for_multi_character_conflict(monkeypatch) -> None:
    called = False

    def fake_writer(_path: str) -> str:
        nonlocal called
        called = True
        return "unused.png"

    monkeypatch.setattr(review, "write_mild_review_image", fake_writer)
    result = review.review_gpu_variant_conflict(
        "original.png",
        _result(CORRECT),
        _result("S07336-VLHL-MDZH-6ABML"),
        lambda _path: (_result(CORRECT), 1),
    )

    assert result.resolved is False
    assert called is False
