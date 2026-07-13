from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import statistics
import time
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class ImageBenchmarkCase:
    name: str
    image: Path
    expected_pubg: tuple[str, ...] = tuple()
    expected_psn: tuple[str, ...] = tuple()
    profile: str = "unspecified"


@dataclass(frozen=True)
class ImageBenchmarkResult:
    name: str
    profile: str
    expected_pubg: tuple[str, ...]
    expected_psn: tuple[str, ...]
    actual_pubg: tuple[str, ...]
    actual_psn: tuple[str, ...]
    missing: tuple[str, ...]
    false_positive: tuple[str, ...]
    type_mix: bool
    order_match: bool
    elapsed_ms: float


@dataclass(frozen=True)
class ImageBenchmarkSummary:
    cases: int
    expected_cards: int
    correct_cards: int
    missing_cards: int
    false_positive_cards: int
    type_mix_cases: int
    order_mismatch_cases: int
    exact_image_matches: int
    precision: float
    recall: float
    p50_ms: float
    p95_ms: float


def load_image_benchmark_cases(manifest_path: Path) -> list[ImageBenchmarkCase]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    cases: list[ImageBenchmarkCase] = []
    for item in payload.get("cases", []):
        image = (root / str(item["image"])).resolve()
        if not image.is_file():
            raise FileNotFoundError(f"Benchmark image not found: {image}")
        cases.append(
            ImageBenchmarkCase(
                name=str(item["name"]),
                image=image,
                expected_pubg=tuple(item.get("expected_pubg", [])),
                expected_psn=tuple(item.get("expected_psn", [])),
                profile=str(item.get("profile", "unspecified")),
            )
        )
    if not cases:
        raise ValueError("Benchmark manifest must contain at least one confirmed case")
    return cases


def run_image_benchmark(
    cases: Iterable[ImageBenchmarkCase],
    recognize: Callable[[Path], Any],
) -> tuple[list[ImageBenchmarkResult], ImageBenchmarkSummary]:
    results: list[ImageBenchmarkResult] = []
    for case in cases:
        started_at = time.perf_counter()
        prediction = recognize(case.image)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        actual_pubg = tuple(prediction.cards)
        actual_psn = tuple(
            getattr(prediction, "psn_ordered", tuple())
            or getattr(prediction, "psn_cards", tuple())
        )
        expected = case.expected_pubg + case.expected_psn
        actual = actual_pubg + actual_psn
        missing = tuple(card for card in expected if card not in actual)
        false_positive = tuple(card for card in actual if card not in expected)
        results.append(
            ImageBenchmarkResult(
                name=case.name,
                profile=case.profile,
                expected_pubg=case.expected_pubg,
                expected_psn=case.expected_psn,
                actual_pubg=actual_pubg,
                actual_psn=actual_psn,
                missing=missing,
                false_positive=false_positive,
                type_mix=bool(actual_pubg and actual_psn),
                order_match=actual == expected,
                elapsed_ms=elapsed_ms,
            )
        )
    return results, summarize_image_benchmark(results)


def summarize_image_benchmark(
    results: Iterable[ImageBenchmarkResult],
) -> ImageBenchmarkSummary:
    rows = list(results)
    if not rows:
        raise ValueError("Cannot summarize an empty benchmark")
    expected_cards = sum(
        len(row.expected_pubg) + len(row.expected_psn) for row in rows
    )
    missing_cards = sum(len(row.missing) for row in rows)
    false_positive_cards = sum(len(row.false_positive) for row in rows)
    correct_cards = expected_cards - missing_cards
    predicted_cards = correct_cards + false_positive_cards
    timings = sorted(row.elapsed_ms for row in rows)
    p95_index = min(len(timings) - 1, max(0, int(len(timings) * 0.95)))
    return ImageBenchmarkSummary(
        cases=len(rows),
        expected_cards=expected_cards,
        correct_cards=correct_cards,
        missing_cards=missing_cards,
        false_positive_cards=false_positive_cards,
        type_mix_cases=sum(row.type_mix for row in rows),
        order_mismatch_cases=sum(not row.order_match for row in rows),
        exact_image_matches=sum(
            not row.missing and not row.false_positive and row.order_match
            for row in rows
        ),
        precision=(correct_cards / predicted_cards) if predicted_cards else 1.0,
        recall=(correct_cards / expected_cards) if expected_cards else 1.0,
        p50_ms=statistics.median(timings),
        p95_ms=timings[p95_index],
    )


def write_image_benchmark_report(
    output_path: Path,
    results: Iterable[ImageBenchmarkResult],
    summary: ImageBenchmarkSummary,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": asdict(summary),
        "cases": [asdict(row) for row in results],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
