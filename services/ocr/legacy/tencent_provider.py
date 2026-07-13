from __future__ import annotations

from pathlib import Path

from services.ocr.base import OcrTextResult


class TencentOcrProvider:
    """历史预留接口，当前未启用。"""

    def recognize(self, image_path: Path) -> OcrTextResult:
        raise NotImplementedError("Tencent OCR provider is not enabled.")
