from __future__ import annotations

import argparse
from pathlib import Path

from services.ocr.gold_dataset import collect_gold_dataset_cases, write_gold_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a private OCR gold dataset from confirmed visual audits")
    parser.add_argument("audit_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/ocr/private/gold"))
    args = parser.parse_args()

    audit_files = sorted(args.audit_dir.glob("*-audit.json"))
    cases = collect_gold_dataset_cases(audit_files)
    manifest = write_gold_dataset(args.output, cases)
    print(f"audit_files={len(audit_files)} confirmed_unique_images={len(cases)} manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
