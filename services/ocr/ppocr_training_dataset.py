from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from services.ocr.image_preprocess import crop_card_roi


def build_ppocr_recognition_candidates(
    manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Build private, confirmed single-card crops for offline PP-OCR training.

    Ambiguous and multi-card cases are intentionally excluded from recognition
    labels and written to an annotation queue instead.
    """

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    sample_dir = output_dir / "images"
    sample_dir.mkdir(parents=True, exist_ok=True)
    labels: list[str] = []
    metadata: list[dict[str, Any]] = []
    annotation_queue: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for case in payload.get("cases", []):
        image_path = (manifest_path.parent / str(case.get("image", ""))).resolve()
        if not image_path.is_file():
            continue
        declared_hash = str(case.get("image_sha256", "")).strip().lower()
        image_hash = _sha256(image_path)
        if declared_hash and declared_hash != image_hash:
            raise ValueError(f"Image hash mismatch: {image_path}")
        if image_hash in seen_hashes:
            continue
        seen_hashes.add(image_hash)

        pubg = tuple(str(value).upper() for value in case.get("expected_pubg", []))
        psn = tuple(str(value).upper() for value in case.get("expected_psn", []))
        profile = str(case.get("profile", "unspecified"))
        if len(pubg) != 1 or psn:
            annotation_queue.append(
                _annotation_item(case, image_hash, pubg, psn, "not_single_pubg")
            )
            continue

        with Image.open(image_path) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
        roi, crop_failed = crop_card_roi(source)
        if crop_failed or roi.width < roi.height * 2:
            annotation_queue.append(
                _annotation_item(case, image_hash, pubg, psn, "unsafe_auto_crop")
            )
            continue

        filename = f"{image_hash}.png"
        relative_path = Path("images") / filename
        roi.save(sample_dir / filename, format="PNG", optimize=True)
        labels.append(f"{relative_path.as_posix()}\t{pubg[0]}")
        metadata.append(
            {
                "case_id": str(case.get("name", image_hash[:16])),
                "image_sha256": image_hash,
                "profile": profile,
                "label": pubg[0],
                "crop_size": [roi.width, roi.height],
            }
        )

    _write_text_atomic(output_dir / "rec_gt_train.txt", "\n".join(labels) + ("\n" if labels else ""))
    _write_json_atomic(
        output_dir / "metadata.json",
        {"schema_version": 1, "samples": metadata},
    )
    _write_json_atomic(
        output_dir / "needs_annotation.json",
        {"schema_version": 1, "cases": annotation_queue},
    )
    return {
        "samples": len(metadata),
        "needs_annotation": len(annotation_queue),
        "duplicates_skipped": len(payload.get("cases", [])) - len(seen_hashes),
    }


def _annotation_item(
    case: dict[str, Any],
    image_hash: str,
    pubg: tuple[str, ...],
    psn: tuple[str, ...],
    reason: str,
) -> dict[str, Any]:
    return {
        "case_id": str(case.get("name", image_hash[:16])),
        "image": str(case.get("image", "")),
        "image_sha256": image_hash,
        "profile": str(case.get("profile", "unspecified")),
        "expected_pubg": list(pubg),
        "expected_psn": list(psn),
        "reason": reason,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)
