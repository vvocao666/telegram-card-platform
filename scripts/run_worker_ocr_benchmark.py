from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the private OCR gold dataset directly against the RTX5070 Worker"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000/ocr")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = list(payload.get("cases", []))
    if args.limit > 0:
        cases = cases[: args.limit]

    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=args.timeout) as client:
        for index, case in enumerate(cases, start=1):
            image_path = (manifest_path.parent / str(case["image"])).resolve()
            expected_pubg = tuple(str(value) for value in case.get("expected_pubg", []))
            expected_psn = tuple(str(value) for value in case.get("expected_psn", []))
            started_at = time.perf_counter()
            try:
                with image_path.open("rb") as image:
                    response = client.post(
                        args.url,
                        files={"file": (image_path.name, image, _content_type(image_path))},
                    )
                response.raise_for_status()
                worker = response.json()
                actual_pubg, actual_psn = _worker_cards(worker)
                error = ""
            except Exception as exc:
                worker = {}
                actual_pubg, actual_psn = (), ()
                error = f"{type(exc).__name__}: {exc}"
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            results.append(
                {
                    "name": str(case.get("name", image_path.stem)),
                    "profile": str(case.get("profile", "unspecified")),
                    "expected_pubg": list(expected_pubg),
                    "expected_psn": list(expected_psn),
                    "actual_pubg": list(actual_pubg),
                    "actual_psn": list(actual_psn),
                    "exact": actual_pubg == expected_pubg and actual_psn == expected_psn,
                    "latency_ms": elapsed_ms,
                    "worker_latency_ms": int(worker.get("latency_ms", 0) or 0),
                    "latency_original_ms": int(worker.get("latency_original_ms", 0) or 0),
                    "latency_enhanced_ms": int(worker.get("latency_enhanced_ms", 0) or 0),
                    "enhanced_used": bool(worker.get("enhanced_used", False)),
                    "best_engine": str(worker.get("best_engine", "")),
                    "cached": bool(worker.get("cached", False)),
                    "variant_review": worker.get("variant_review", {}),
                    "cpu_ocr": worker.get("cpu_ocr", {}),
                    "error": error,
                }
            )
            print(
                f"[{index}/{len(cases)}] exact={results[-1]['exact']} "
                f"latency_ms={elapsed_ms} enhanced={results[-1]['enhanced_used']} "
                f"name={results[-1]['name']}",
                flush=True,
            )

    report = _report(results)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"report={args.output}")
    return 0 if report["summary"]["request_errors"] == 0 else 1


def _worker_cards(worker: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    pubg: list[str] = []
    psn: list[str] = []
    for item in worker.get("cards", []) or []:
        text = str(item.get("text", "") if isinstance(item, dict) else item).strip().upper()
        if not text:
            continue
        target = pubg if text.startswith("S07") else psn
        if text not in target:
            target.append(text)
    return tuple(pubg), tuple(psn)


def _report(results: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [int(item["latency_ms"]) for item in results if not item["error"]]
    exact = sum(bool(item["exact"]) for item in results)
    enhanced = sum(bool(item["enhanced_used"]) for item in results)
    cached = sum(bool(item["cached"]) for item in results)
    variant_reviews = sum(
        bool((item.get("variant_review") or {}).get("review_card")) for item in results
    )
    summary = {
        "cases": len(results),
        "exact_matches": exact,
        "exact_rate": round(exact / len(results), 4) if results else 0.0,
        "request_errors": sum(bool(item["error"]) for item in results),
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "enhanced_count": enhanced,
        "enhanced_rate": round(enhanced / len(results), 4) if results else 0.0,
        "cache_hits": cached,
        "variant_reviews": variant_reviews,
    }
    return {"schema_version": 1, "summary": summary, "cases": results}


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return int(round(ordered[lower] * (1 - weight) + ordered[upper] * weight))


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".webp"}:
        return "image/webp"
    return "image/jpeg"


if __name__ == "__main__":
    raise SystemExit(main())
