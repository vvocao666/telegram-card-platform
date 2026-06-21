from __future__ import annotations

from pathlib import Path

from services.ocr.base import OcrTextResult


class TencentOcrProvider:
    """腾讯 OCR 预留接口；密钥必须从 .env 读取，不能写死。"""

    def recognize(self, image_path: Path) -> OcrTextResult:
        raise NotImplementedError("Tencent OCR provider is reserved but not enabled.")
