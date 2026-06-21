from __future__ import annotations

from pathlib import Path

from services.ocr.base import OcrTextResult


class OcrSpaceProvider:
    """OCR.space 适配器占位。

    当前生产实现仍在 bot.py 的 run_ocrspace。保留这个类是为了新项目能按供应商切换。
    """

    def recognize(self, image_path: Path) -> OcrTextResult:
        from bot import run_ocrspace

        result = run_ocrspace(image_path)
        return OcrTextResult(raw_text=result.raw_text, provider="ocrspace")
