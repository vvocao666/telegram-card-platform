from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class OcrTextResult:
    raw_text: str
    provider: str


class OcrProvider(Protocol):
    """OCR Provider 的最小文本接口。"""

    def recognize(self, image_path: Path) -> OcrTextResult:
        ...
