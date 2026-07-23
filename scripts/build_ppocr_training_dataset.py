from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ocr.ppocr_training_dataset import build_ppocr_recognition_candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build private PP-OCR recognition candidates from the OCR gold dataset"
    )
    parser.add_argument(
        "manifest",
        type=Path,
        default=Path("benchmarks/ocr/private/gold/manifest.json"),
        nargs="?",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/ocr/private/ppocr-training"),
    )
    args = parser.parse_args()
    summary = build_ppocr_recognition_candidates(args.manifest.resolve(), args.output.resolve())
    print(
        "samples={samples} needs_annotation={needs_annotation} "
        "duplicates_skipped={duplicates_skipped} output={output}".format(
            output=args.output,
            **summary,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
