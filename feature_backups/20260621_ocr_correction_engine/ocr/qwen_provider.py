from __future__ import annotations

from pathlib import Path

from services.ocr.base import OcrTextResult


class QwenVisionProvider:
    """Qwen/视觉模型预留接口，用于后续处理难识别字体。"""

    def recognize(self, image_path: Path) -> OcrTextResult:
        raise NotImplementedError("Qwen vision provider is reserved but not enabled.")
