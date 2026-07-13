from __future__ import annotations

import argparse
from pathlib import Path

from services.ocr.adaptive_optimizer import (
    build_adaptive_policy_candidates,
    load_adaptive_audit_cases,
    write_adaptive_policy_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build shadow OCR policy candidates from confirmed audit labels")
    parser.add_argument("audit_dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/ocr_adaptive_policy_candidates.json"),
    )
    args = parser.parse_args()

    audit_files = sorted(args.audit_dir.glob("*-audit.json"))
    cases = load_adaptive_audit_cases(audit_files)
    candidates = build_adaptive_policy_candidates(cases)
    write_adaptive_policy_candidates(args.output, candidates)
    print(
        f"audit_files={len(audit_files)} cases={len(cases)} "
        f"candidates={len(candidates)} eligible={sum(item.eligible for item in candidates)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
