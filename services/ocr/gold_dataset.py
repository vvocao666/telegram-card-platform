from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable


CONFIRMED_STATUSES = {"confirmed_match", "confirmed_error"}


@dataclass(frozen=True)
class GoldDatasetCase:
    case_id: str
    source_image: Path
    image_hash: str
    profile: str
    expected_pubg: tuple[str, ...]
    expected_psn: tuple[str, ...]


def collect_gold_dataset_cases(audit_files: Iterable[Path]) -> list[GoldDatasetCase]:
    cases: list[GoldDatasetCase] = []
    seen_hashes: set[str] = set()
    for audit_file in audit_files:
        payload = json.loads(audit_file.read_text(encoding="utf-8"))
        for item in payload.get("cases", []):
            if str(item.get("status", "")) not in CONFIRMED_STATUSES:
                continue
            source_image = (audit_file.parent / str(item.get("image", ""))).resolve()
            if not source_image.is_file():
                continue
            image_hash = _sha256(source_image)
            declared_hash = str(item.get("image_sha256", "")).strip().lower()
            if declared_hash and declared_hash != image_hash:
                raise ValueError(f"Image hash mismatch: {source_image}")
            if image_hash in seen_hashes:
                continue
            case_id = str(item.get("case_id", "")).strip() or image_hash[:16]
            cases.append(
                GoldDatasetCase(
                    case_id=case_id,
                    source_image=source_image,
                    image_hash=image_hash,
                    profile=str(item.get("profile", "unspecified")) or "unspecified",
                    expected_pubg=tuple(str(value) for value in item.get("expected_pubg", [])),
                    expected_psn=tuple(str(value) for value in item.get("expected_psn", [])),
                )
            )
            seen_hashes.add(image_hash)
    return cases


def write_gold_dataset(output_dir: Path, cases: Iterable[GoldDatasetCase]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    manifest_cases: list[dict[str, object]] = []
    for case in cases:
        suffix = case.source_image.suffix.lower() or ".jpg"
        filename = f"{case.image_hash}{suffix}"
        target = image_dir / filename
        if not target.exists():
            shutil.copy2(case.source_image, target)
        manifest_cases.append(
            {
                "name": case.case_id,
                "image": f"images/{filename}",
                "image_sha256": case.image_hash,
                "profile": case.profile,
                "expected_pubg": list(case.expected_pubg),
                "expected_psn": list(case.expected_psn),
            }
        )
    manifest_path = output_dir / "manifest.json"
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"schema_version": 1, "cases": manifest_cases}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return manifest_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
