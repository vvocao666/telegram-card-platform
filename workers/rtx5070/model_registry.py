from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path


RAPIDOCR_VERSION = "1.4.4"
MODEL_SHA256 = {
    "ch_PP-OCRv4_det_infer.onnx": "d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9",
    "ch_PP-OCRv4_rec_infer.onnx": "48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b",
    "ch_ppocr_mobile_v2.0_cls_infer.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
}


@dataclass(frozen=True)
class CpuModelStatus:
    available: bool
    version: str
    model_fingerprint: str
    error: str = ""


def validate_cpu_model() -> CpuModelStatus:
    """验证固定 CPU OCR 包和内置模型，禁止运行时下载或静默换模型。"""
    try:
        version = metadata.version("rapidocr-onnxruntime")
    except metadata.PackageNotFoundError:
        return CpuModelStatus(False, "", "", "rapidocr_not_installed")
    if version != RAPIDOCR_VERSION:
        return CpuModelStatus(False, version, "", "rapidocr_version_mismatch")

    try:
        import rapidocr_onnxruntime  # type: ignore
    except Exception:
        return CpuModelStatus(False, version, "", "rapidocr_import_failed")
    root = Path(rapidocr_onnxruntime.__file__).resolve().parent
    hashes: list[str] = []
    for name, expected in MODEL_SHA256.items():
        matches = list(root.rglob(name))
        if len(matches) != 1:
            return CpuModelStatus(False, version, "", f"model_missing:{name}")
        digest = _sha256(matches[0])
        if digest != expected:
            return CpuModelStatus(False, version, "", f"model_hash_mismatch:{name}")
        hashes.append(digest)
    fingerprint = hashlib.sha256("|".join(hashes).encode("ascii")).hexdigest()[:16]
    return CpuModelStatus(True, version, fingerprint)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
