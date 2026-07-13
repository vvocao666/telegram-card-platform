from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ocr.image_benchmark import (  # noqa: E402
    load_image_benchmark_cases,
    run_image_benchmark,
    write_image_benchmark_report,
)
from services.runtime import run_ocr  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="运行人工真值图片 OCR benchmark")
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/ocr_benchmark_report.json"),
    )
    args = parser.parse_args()
    cases = load_image_benchmark_cases(args.manifest)
    results, summary = run_image_benchmark(cases, run_ocr)
    write_image_benchmark_report(args.output, results, summary)
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2))
    return int(
        summary.missing_cards > 0
        or summary.false_positive_cards > 0
        or summary.type_mix_cases > 0
        or summary.order_mismatch_cases > 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
