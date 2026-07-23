from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from services.ocr.ppocr_training_dataset import build_ppocr_recognition_candidates


CARD = "S07336-ABCD-EFGH-JKLMN"


def _image(path: Path) -> str:
    image = Image.new("RGB", (600, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 25, 580, 75), fill="black")
    image.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_builds_only_safe_single_pubg_recognition_labels(tmp_path: Path):
    image_path = tmp_path / "single.png"
    image_hash = _image(image_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "single",
                        "image": image_path.name,
                        "image_sha256": image_hash,
                        "profile": "pubg|thin_strip|clear|single",
                        "expected_pubg": [CARD],
                        "expected_psn": [],
                    },
                    {
                        "name": "multi",
                        "image": image_path.name,
                        "image_sha256": image_hash,
                        "profile": "pubg|multi_card|clear|medium",
                        "expected_pubg": [CARD, "S07336-PQRS-TUVW-XYZAB"],
                        "expected_psn": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = build_ppocr_recognition_candidates(manifest, tmp_path / "output")

    assert summary == {
        "samples": 1,
        "needs_annotation": 0,
        "duplicates_skipped": 1,
    }
    labels = (tmp_path / "output" / "rec_gt_train.txt").read_text(encoding="utf-8")
    assert labels.endswith(f"\t{CARD}\n")


def test_multi_card_case_is_never_auto_labeled(tmp_path: Path):
    image_path = tmp_path / "multi.png"
    image_hash = _image(image_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "multi",
                        "image": image_path.name,
                        "image_sha256": image_hash,
                        "profile": "pubg|multi_card|clear|medium",
                        "expected_pubg": [CARD, "S07336-PQRS-TUVW-XYZAB"],
                        "expected_psn": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = build_ppocr_recognition_candidates(manifest, tmp_path / "output")

    assert summary["samples"] == 0
    assert summary["needs_annotation"] == 1
    queue = json.loads(
        (tmp_path / "output" / "needs_annotation.json").read_text(encoding="utf-8")
    )
    assert queue["cases"][0]["reason"] == "not_single_pubg"
