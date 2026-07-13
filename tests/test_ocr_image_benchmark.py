from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from services.ocr.image_benchmark import (
    ImageBenchmarkCase,
    run_image_benchmark,
)


@dataclass(frozen=True)
class Prediction:
    cards: tuple[str, ...]
    psn_cards: tuple[str, ...] = tuple()
    psn_ordered: tuple[str, ...] = tuple()


def test_image_benchmark_measures_exact_cards_order_and_latency(tmp_path: Path):
    image_path = tmp_path / "real-image-path.png"
    Image.new("RGB", (320, 120), "white").save(image_path)
    expected = ("S07336-ABCD-EFGH-JKLMN", "S07336-PQRS-TUVW-XYZ12")
    cases = [
        ImageBenchmarkCase(
            name="ordered",
            image=image_path,
            expected_pubg=expected,
            profile="thin_strip",
        )
    ]

    rows, summary = run_image_benchmark(
        cases,
        lambda _path: Prediction(cards=expected),
    )

    assert rows[0].order_match is True
    assert summary.correct_cards == 2
    assert summary.missing_cards == 0
    assert summary.false_positive_cards == 0
    assert summary.exact_image_matches == 1


def test_image_benchmark_reports_missing_false_positive_and_type_mix(tmp_path: Path):
    image_path = tmp_path / "mixed.png"
    Image.new("RGB", (320, 120), "white").save(image_path)
    cases = [
        ImageBenchmarkCase(
            name="mixed",
            image=image_path,
            expected_pubg=("S07336-ABCD-EFGH-JKLMN",),
        )
    ]

    _rows, summary = run_image_benchmark(
        cases,
        lambda _path: Prediction(
            cards=("S07336-XXXX-YYYY-ZZZZZ",),
            psn_ordered=("ABCD-EFGH-JKLM",),
        ),
    )

    assert summary.missing_cards == 1
    assert summary.false_positive_cards == 2
    assert summary.type_mix_cases == 1
    assert summary.order_mismatch_cases == 1
