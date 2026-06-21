from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class OcrTextResult:
    raw_text: str
    provider: str


class OcrProvider(Protocol):
    """OCR 供应商接口，方便后续接腾讯 OCR、Qwen 视觉模型或本地 PaddleOCR。"""

    def recognize(self, image_path: Path) -> OcrTextResult:
        ...
